#!/usr/bin/env python3
"""
treatment_heterogeneity.py — does a treatment work better for some parts of the patient
spectrum than others?

Approach: join per-(patient, drug) sentiment to the patient's phenotype markers, then for
each drug-class x condition test whether the POSITIVE-response rate differs for patients
WITH vs WITHOUT that condition (Fisher exact, BH-FDR corrected). Reports the strongest,
significant contrasts + a class x condition response-rate heatmap.

This is OBSERVATIONAL self-report (a "what helped me" reporting bias of ~76% positive overall),
the conditions OVERLAP heavily (so condition-specific effects are partly entangled), and it is
NOT causal. It is hypothesis-generating signal of treatment-effect heterogeneity.

Reads (read-only): data/csv_export/drug_sentiment.csv, data/clean/model_matrix.csv,
data/clean/model_matrix_controlled.csv. Writes report + heatmap to data/clean/.
"""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
KEY = "author_hash"
MIN_CELL = 10          # min positive+negative reports per with/without cell
MIN_TOTAL = 40         # min reports for a drug-class to be analyzed

# ---- phenotype markers per patient (the "parts of the spectrum") -------------
ctrl = pd.read_csv(CLEAN / "model_matrix_controlled.csv")
full = pd.read_csv(CLEAN / "model_matrix.csv").set_index(KEY)
CONDS = ["pots", "mcas", "dysautonomia", "me_cfs", "pem", "small_fiber_neuropathy", "fibromyalgia"]
marker = pd.DataFrame({KEY: ctrl[KEY]})
for c in CONDS:
    col = f"conditions={c}"
    marker[c] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
marker["eds_any"] = ctrl["eds_any"].to_numpy()
CONDS = CONDS + ["eds_any"]
marker = marker.set_index(KEY)

# ---- drug sentiment, mapped to clinical classes ------------------------------
ds = pd.read_csv(CLEAN.parent / "csv_export" / "drug_sentiment.csv")
ds = ds[ds["sentiment"].isin(["positive", "negative", "mixed"])].copy()
ds["d"] = ds["drug"].astype(str).str.lower()

CLASSES = {
    "LDN (naltrexone)":        r"naltrexone|ldn",
    "antihistamine (H1/H2)":   r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|\bh1\b|\bh2\b",
    "mast-cell stabilizer":    r"cromolyn|ketotifen|quercetin|mast cell",
    "beta blocker":            r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol",
    "ivabradine":              r"ivabradine|corlanor",
    "POTS volume (salt/fludro/midodrine)": r"midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression",
    "SSRI/SNRI":               r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta",
    "metformin":               r"metformin",
    "paxlovid/antiviral":      r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir",
    "anticoagulant/nattokinase": r"nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban|triple anticoag",
    "magnesium":               r"magnesium",
    "CoQ10/mito":              r"coq10|coenzyme|ubiquinol",
    "B12/B-complex":           r"\bb12\b|b-12|methylcobalamin|b complex|b-complex|b vitamin",
    "vitamin D":               r"vitamin d|\bvit d\b",
    "LDA (low-dose abilify)":  r"abilify|aripiprazole",
}

# attach patient markers to each report
ds = ds.join(marker, on="user_id")
for c in CONDS:
    ds[c] = ds[c].fillna(0).astype(int)
ds["pos"] = (ds["sentiment"] == "positive").astype(int)
ds["neg"] = (ds["sentiment"] == "negative").astype(int)

def bh_fdr(pvals):
    p = np.asarray(pvals, float); n = len(p); order = np.argsort(p)
    q = np.empty(n); prev = 1.0
    for rank, idx in enumerate(reversed(order)):
        i = n - rank
        prev = min(prev, p[idx] * n / i); q[idx] = prev
    return q

rows, heat_rate, heat_n = [], {}, {}
report = []
def w(s=""):
    report.append(s); print(s)

w(f"TREATMENT-EFFECT HETEROGENEITY ACROSS THE SPECTRUM")
w(f"{len(ds)} drug reports | overall positive rate "
  f"{ds['pos'].sum()/(ds['pos'].sum()+ds['neg'].sum())*100:.0f}% (of pos+neg)")
w(f"min {MIN_TOTAL} reports/class, min {MIN_CELL} pos+neg per with/without cell\n")

for cls, pat in CLASSES.items():
    sub = ds[ds["d"].str.contains(pat, regex=True, na=False)]
    npn = int(sub["pos"].sum() + sub["neg"].sum())
    if npn < MIN_TOTAL:
        continue
    base = sub["pos"].sum() / npn
    heat_rate[cls], heat_n[cls] = {}, {}
    heat_rate[cls]["ALL"], heat_n[cls]["ALL"] = base, npn
    for c in CONDS:
        wsub, osub = sub[sub[c] == 1], sub[sub[c] == 0]
        pw, nw = int(wsub["pos"].sum()), int(wsub["neg"].sum())
        po, no = int(osub["pos"].sum()), int(osub["neg"].sum())
        if pw + nw < MIN_CELL or po + no < MIN_CELL:
            continue
        rate_w, rate_o = pw / (pw + nw), po / (po + no)
        heat_rate[cls][c], heat_n[cls][c] = rate_w, pw + nw
        _, p = fisher_exact([[pw, nw], [po, no]])
        rows.append(dict(cls=cls, cond=c, rate_with=rate_w, rate_without=rate_o,
                         delta=rate_w - rate_o, n_with=pw + nw, n_without=po + no, p=p))

res = pd.DataFrame(rows)
res["q"] = bh_fdr(res["p"].values)
res = res.sort_values("delta", key=lambda s: -s.abs())

w("== strongest heterogeneity contrasts (positive-rate WITH vs WITHOUT the condition) ==")
w(f"  {'drug class':<34}{'condition':<14}{'with':>10}{'without':>9}{'delta':>8}{'p':>8}{'q(FDR)':>8}")
w("  " + "-" * 91)
for _, r in res.iterrows():
    star = "*" if r["q"] < 0.10 else " "
    w(f" {star}{r['cls']:<34}{r['cond']:<14}"
      f"{r['rate_with']*100:5.0f}% (n{r['n_with']:<3}) {r['rate_without']*100:4.0f}% "
      f"{r['delta']*100:+6.0f}pp {r['p']:7.3f} {r['q']:7.3f}")

w("\n  * = FDR q<0.10. delta = (positive rate among patients WITH the condition) - (WITHOUT).")
w("  Positive delta => the class is reported to work better for that part of the spectrum.")
w("\n  CAVEATS: observational self-report with a ~76% 'what-helped-me' positivity bias; the")
w("  conditions OVERLAP (POTS/MCAS/dysautonomia/EDS co-occur) so effects are partly entangled;")
w("  selection (who tries/ reports what) is uncontrolled. This is hypothesis-generating, NOT")
w("  efficacy. A multivariable model (positive ~ all conditions, per drug) is the next step to")
w("  disentangle the overlap.")

(CLEAN / "treatment_heterogeneity_report.txt").write_text("\n".join(report), encoding="utf-8")

# ---- heatmap: class x condition positive-rate (mask thin cells) --------------
cols = ["ALL"] + CONDS
H = pd.DataFrame(index=list(heat_rate), columns=cols, dtype=float)
A = pd.DataFrame("", index=list(heat_rate), columns=cols)
for cls in heat_rate:
    for c in cols:
        if c in heat_rate[cls]:
            H.loc[cls, c] = heat_rate[cls][c] * 100
            A.loc[cls, c] = f"{heat_rate[cls][c]*100:.0f}\n(n{heat_n[cls][c]})"
plt.figure(figsize=(11, 8))
sns.heatmap(H.astype(float), annot=A.values, fmt="", cmap="RdYlGn", center=70,
            vmin=30, vmax=100, linewidths=.5, cbar_kws={"label": "% positive (of pos+neg)"})
plt.title("Treatment positive-response rate by part of the spectrum\n"
          "(rows=drug class, cols=condition; n = pos+neg reports; thin cells blank)")
plt.tight_layout()
plt.savefig(CLEAN / "figures" / "treatment_heterogeneity.png", dpi=120)
plt.close()

print(f"\nwrote: data/clean/treatment_heterogeneity_report.txt")
print(f"wrote: data/clean/figures/treatment_heterogeneity.png")
