#!/usr/bin/env python3
"""
clean_encode.py - turn data/csv_export/patients_wide.csv into a clean, multi-hot
patient x variable matrix for analysis.

Project decisions baked in:
  * KEEP ALL FIELDS - nothing is dropped, including "medically insignificant" ones.
    They are TAGGED (field_dictionary.csv `category`) in the manifest so you can filter
    later, but every field is retained.
  * SPLIT multi-value fields ("a | b | c") into MULTIPLE 0/1 dummy variables (multi-hot).
  * CONSOLIDATE values via VOCAB (synonym/variant grouping). EXTEND VOCAB to group more
    (drug classes, symptom domains, etc.) - that's where clinical grouping lives.
  * GRANULARITY knob: a value needs >= MIN_PATIENTS to get its own column; rarer values
    fold into "<field>__other". NOTHING IS LOST - the exact values remain in the raw
    CSVs, and __other preserves that the patient had some uncommon value. Lower
    MIN_PATIENTS for finer columns, raise it to consolidate more.
  * NON-DESTRUCTIVE: reads raw, writes only to data/clean/. Asserts row count preserved.
  * AUDITABLE: writes column_manifest.csv + cleaning_report.txt; prints an audit summary.

Outputs (data/clean/):
  model_matrix.csv     - author_hash + numeric cols + 0/1 dummy cols (one row per patient)
  column_manifest.csv  - one row per output column: column, field, value, type, category, n_patients
  cleaning_report.txt  - per-field audit
"""
from __future__ import annotations
import csv, re
from collections import Counter
from pathlib import Path

# ----- knobs (edit these) ---------------------------------------------------
MIN_PATIENTS   = 5          # value needs >= this many patients for its own column; rest -> <field>__other
SEP            = " | "
KEY            = "author_hash"
NUMERIC_FIELDS = {"age", "age_at_onset", "long_covid_duration_months", "infection_count"}
META = {"author_hash", "source", "source_type", "post_id", "text_count", "schema_id",
        "extraction_method", "extracted_at", "aggregated", "n_items", "num_comments"}

# Consolidation vocab: field -> {canonical: [surface forms]}. EXTEND to group more.
# Values not listed are just lowercased/stripped (and still encoded).
VOCAB = {
  "conditions": {
    "long_covid": ["long covid", "long-covid", "lc", "pasc", "post covid", "post-covid", "long hauler", "longhauler"],
    "me_cfs": ["me/cfs", "mecfs", "me cfs", "cfs", "chronic fatigue syndrome", "chronic fatigue"],
    "pem": ["pem", "post-exertional malaise", "post exertional malaise", "post exertional"],
    "pots": ["pots", "postural orthostatic tachycardia syndrome", "postural tachycardia", "postural orthostatic tachycardia"],
    "dysautonomia": ["dysautonomia", "autonomic dysfunction", "autonomic neuropathy"],
    "mcas": ["mcas", "mast cell activation syndrome", "mast cell activation", "mast cell", "histamine intolerance"],
    "eds": ["ehlers-danlos syndrome", "ehlers danlos", "eds", "heds", "hypermobility", "hypermobile"],
    "small_fiber_neuropathy": ["small fiber neuropathy", "sfn", "small fibre neuropathy"],
    "fibromyalgia": ["fibromyalgia", "fibro"],
    "post_viral": ["post-viral", "post viral", "postviral"],
    "ms": ["ms", "multiple sclerosis"],
    "ibs": ["ibs", "irritable bowel"],
    "gastroparesis": ["gastroparesis"],
    "lyme": ["lyme", "lyme disease", "chronic lyme"],
    "lupus": ["lupus", "sle"],
    "hashimotos": ["hashimoto's", "hashimotos", "hashimoto", "hashimotos thyroiditis"],
  },
  "treatment_outcome": {
    "helped": ["helped", "better", "improved", "improvement", "worked", "helps", "helpful"],
    "no_effect": ["no effect", "no_effect", "no difference", "no change", "didn't work", "didnt work",
                  "didn't help", "didnt help", "no benefit", "nothing"],
    "worsened": ["worsened", "worse", "made it worse", "made worse", "negative", "bad reaction", "crashed", "adverse"],
  },
  "medication_trial_outcome_category": {
    "helped": ["helped", "better", "improved", "worked"],
    "no_effect": ["no effect", "no_effect", "doesn't work", "doesn't help", "didn't work", "no difference"],
    "worsened": ["worsened", "worse", "flare up", "flare", "made it worse", "bad reaction"],
  },
  "symptom_trajectory": {
    "improving": ["improving", "improved", "getting better", "recovering"],
    "recovered": ["recovered", "recovery", "remission", "fully recovered"],
    "declining": ["worsening", "worse", "severe decline", "declining", "progressive", "deteriorating"],
    "relapsing": ["relapsing", "relapsing-remitting", "fluctuating", "up and down", "remitting", "waxing and waning"],
    "stable": ["stable", "plateau", "plateaued", "same", "unchanged"],
  },
  "functional_status_tier": {
    "bedbound": ["bedbound", "bedridden", "bed bound", "mostly in bed"],
    "housebound": ["housebound", "homebound", "house bound"],
    "mobility_limited": ["wheelchair", "rollator", "walker", "mobility aid", "cane", "mobility scooter"],
    "working_limited": ["working part time", "part time", "reduced hours", "working"],
    "severe": ["severe", "very severe"],
  },
  "medications": {  # STARTER - extend with drug-class grouping as needed
    "ldn": ["ldn", "low dose naltrexone", "low-dose naltrexone", "naltrexone"],
  },
}

_PUNCT = re.compile(r"[^\w%/+\-' ]+")
_WS = re.compile(r"\s+")

def clean(s: str) -> str:
    s = (s or "").strip().lower().replace("’", "'")
    return _WS.sub(" ", _PUNCT.sub(" ", s)).strip()

def build_lut(vocab):
    lut = {}
    for canon, surfaces in vocab.items():
        lut[clean(canon)] = canon
        for x in surfaces:
            lut[clean(x)] = canon
    return lut

LUT = {f: build_lut(v) for f, v in VOCAB.items()}

# Regex normalization for free-text fields the exact-match VOCAB can't cover (e.g.
# symptom_trajectory had "80% recovered", "push-crash", "slowly getting better", ...).
# Rules are tried in order; first match wins; runs before the exact LUT.
REGEX_RULES = {
    "symptom_trajectory": [
        (re.compile(r"relaps|fluctuat|\bwax|comes and goes|push.?crash|remitting"), "relapsing"),
        (re.compile(r"(fully |mostly )?recovered|resolved|remission|\d+\s*%\s*recover"), "recovered"),
        (re.compile(r"improv|better|recovering"), "improving"),
        (re.compile(r"declin|worsen|progressive|deteriorat|set.?back|getting worse"), "declining"),
        (re.compile(r"stable|persistent|permanent|plateau|unchanged|no improvement|not improv|not getting better|no change"), "stable"),
    ],
}

def normalize(field, val):
    c = clean(val)
    if not c:
        return None
    for rx, canon in REGEX_RULES.get(field, []):
        if rx.search(c):
            return canon
    lut = LUT.get(field)
    return lut.get(c, c) if lut else c

def parse_num(val):
    m = re.search(r"-?\d+(?:\.\d+)?", val or "")
    return m.group(0) if m else ""

# ----- load -----------------------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "data" / "csv_export" / "patients_wide.csv"
FDP = ROOT / "data" / "field_dictionary.csv"
OUT = ROOT / "data" / "clean"; OUT.mkdir(parents=True, exist_ok=True)

with open(SRC, encoding="utf-8", newline="") as f:
    rows = list(csv.DictReader(f))
N = len(rows)
cols = list(rows[0].keys())
cat = {}
if FDP.exists():
    for r in csv.DictReader(open(FDP, encoding="utf-8")):
        cat[r["field"]] = r.get("category", "")

# Scope the FEATURE matrix to the canonical 95 fields (the codebook). patients_wide.csv
# (the unified DB view) also carries build_unified extras we intentionally keep OUT of the
# matrix (they remain untouched in the raw CSV -- nothing is deleted from source):
#   demo_*                      a 2nd, complementary demographics source (redundant with the
#                               age/sex_gender/location_* fields already in the 95)
#   drugs_*, n_drug_reports     the treatment OUTCOME (using as features would leak the signal)
#   5 misspelled fields         verified empty (0/N) artifacts of the 2-run merge / discovery typos
codebook_fields = set(cat) if cat else None
if codebook_fields:
    data_fields = [c for c in cols if c not in META and c in codebook_fields]
else:                                   # no codebook -> fall back to all non-meta
    data_fields = [c for c in cols if c not in META]
excluded = [c for c in cols if c not in META and c not in (codebook_fields or set(cols))]
numeric = [f for f in data_fields if f in NUMERIC_FIELDS]
categ = [f for f in data_fields if f not in NUMERIC_FIELDS]

# ----- encode ---------------------------------------------------------------
out = {KEY: [r.get(KEY, "") for r in rows]}
manifest, report = [], []

for f in numeric:
    vals = [parse_num(r.get(f, "")) for r in rows]
    n_ok = sum(1 for v in vals if v != "")
    out[f] = vals
    manifest.append((f, f, "(numeric)", "numeric", cat.get(f, ""), n_ok))
    report.append(f"[numeric ] {f:40} parsed {n_ok}/{N} ({100*n_ok//N}%)")

for f in categ:
    pat_vals, cnt, raw_distinct = [], Counter(), set()
    for r in rows:
        s = set()
        for piece in (r.get(f, "") or "").split(SEP):
            raw = piece.strip().lower()
            if raw:
                raw_distinct.add(raw)
            v = normalize(f, piece)
            if v:
                s.add(v)
        pat_vals.append(s)
        cnt.update(s)
    kept = [v for v, c in cnt.most_common() if c >= MIN_PATIENTS]
    rare = {v for v, c in cnt.items() if c < MIN_PATIENTS}
    for v in kept:
        col = f"{f}={v}"
        out[col] = [1 if v in s else 0 for s in pat_vals]
        manifest.append((col, f, v, "dummy", cat.get(f, ""), cnt[v]))
    if rare:
        col = f"{f}__other"
        out[col] = [1 if (s & rare) else 0 for s in pat_vals]
        manifest.append((col, f, "(rare/other)", "dummy", cat.get(f, ""), sum(out[col])))
    coverage = sum(1 for s in pat_vals if s)
    report.append(f"[multihot] {f:40} cov {coverage:4}/{N} ({100*coverage//N:3}%) | "
                  f"distinct raw {len(raw_distinct):4} -> canon {len(cnt):4} -> {len(kept):3} cols"
                  f"{' +other' if rare else ''} | vocab={'YES' if f in VOCAB else 'no'}")

# ----- write + validate -----------------------------------------------------
columns = list(out.keys())
assert all(len(v) == N for v in out.values()), "ROW COUNT MISMATCH - aborting"

with open(OUT / "model_matrix.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(columns)
    for i in range(N):
        w.writerow([out[c][i] for c in columns])
with open(OUT / "column_manifest.csv", "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f); w.writerow(["column", "field", "value", "type", "field_category", "n_patients"])
    w.writerows(manifest)
with open(OUT / "cleaning_report.txt", "w", encoding="utf-8") as f:
    f.write(f"clean_encode | {N} patients | MIN_PATIENTS={MIN_PATIENTS}\n")
    f.write(f"output: {N} x {len(columns)} = 1 id + {len(numeric)} numeric + "
            f"{len(columns)-1-len(numeric)} dummy columns\n")
    f.write(f"fields encoded: {len(data_fields)} codebook fields\n")
    f.write(f"excluded from matrix (kept in raw patients_wide.csv): {sorted(excluded)}\n\n")
    f.write("\n".join(sorted(report)))

# ----- audit summary to stdout ----------------------------------------------
ndummy = len(columns) - 1 - len(numeric)
print(f"patients:            {N}")
print(f"fields encoded:      {len(data_fields)}  (the canonical codebook fields)")
print(f"excluded from matrix (kept in raw patients_wide.csv): {len(excluded)}")
if excluded:
    print("  " + ", ".join(sorted(excluded)))
print(f"output matrix:       {N} x {len(columns)}  -> data/clean/model_matrix.csv")
print(f"  = 1 id + {len(numeric)} numeric + {ndummy} dummy columns  (MIN_PATIENTS={MIN_PATIENTS})")
fcount = Counter(m[1] for m in manifest if m[3] == "dummy")
print("\nwidest fields (most dummy columns):")
for fld, n in fcount.most_common(12):
    print(f"  {fld:42} {n}")
empty = [f for f in categ if fcount.get(f, 0) == 0]
print(f"\nfields with 0 kept columns (all values < {MIN_PATIENTS} patients -> only __other): {len(empty)}")
if empty:
    print("  " + ", ".join(empty[:12]) + (" ..." if len(empty) > 12 else ""))
print("\nfull per-field audit -> data/clean/cleaning_report.txt")
print("manifest (what each column means) -> data/clean/column_manifest.csv")
