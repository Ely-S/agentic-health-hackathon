#!/usr/bin/env python3
"""
verbosity_control.py — measure and control the verbosity confound in the cleaned
patient matrix, and validate the condition canonicals Eli flagged (me_cfs / ms / eds).

The matrix is presence-encoded: a `0` means "didn't mention it," not "doesn't have it."
Patients who fill more fields carry more 1s, so naive similarity ranks *verbose* patients
as similar regardless of phenotype. This script:

  Step 0   — diagnose: n_fields_filled, PCA corr(PC1, n_fields), KMeans silhouette +
             verbosity-leakage eta^2.
  Step 0.5 — validate condition canonicalization (me_cfs/ms have no false positives;
             build eds_any = conditions ∪ connective_tissue_symptoms; addresses Eli).
  Playbook — A restrict to analysis-grade fields, B IDF-weight, C L2-normalize (cosine);
             re-diagnose after each. Residualize n_fields only if still confounded.

Reads (read-only): data/clean/model_matrix.csv, data/clean/column_manifest.csv,
  data/field_dictionary.csv, data/patientpunk.db.
Writes (gitignored): data/clean/verbosity_report.txt, data/clean/model_matrix_controlled.csv,
  data/clean/figures/pca_verbosity_{before,after}.png.
Non-destructive. Mirrors the silhouette/readiness idea from PatientPunk's cluster_prep.py
(readiness_report) but is self-contained — no cross-repo import.
"""
from __future__ import annotations
import math, sqlite3, re
from pathlib import Path
from collections import defaultdict
import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score
from scipy.stats import pearsonr, spearmanr
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
FIG = CLEAN / "figures"; FIG.mkdir(parents=True, exist_ok=True)
DB = ROOT / "data" / "patientpunk.db"
KEY = "author_hash"
NUMERIC = {"age", "age_at_onset", "infection_count", "long_covid_duration_months"}
SEED = 0
KRANGE = range(2, 9)
PCS = 10                     # components used for clustering / leakage

# ---------------------------------------------------------------- load --------
df = pd.read_csv(CLEAN / "model_matrix.csv")
man = {m["column"]: m for m in pd.read_csv(CLEAN / "column_manifest.csv").to_dict("records")}
fd = {r["field"]: r for r in pd.read_csv(ROOT / "data" / "field_dictionary.csv").to_dict("records")}
ids = df[KEY].astype(str).tolist()
N = len(ids)

dummy_cols = [c for c in df.columns if man.get(c, {}).get("type") == "dummy"]
P = df[dummy_cols].to_numpy(dtype=float)                       # N x D presence (0/1)
col_field = {c: man[c]["field"] for c in dummy_cols}
col_df = {c: int(man[c]["n_patients"]) for c in dummy_cols}    # document frequency
pos = {c: j for j, c in enumerate(dummy_cols)}

# verbosity measures (computed ONCE on the full matrix; same nuisance for every rep)
field_cols = defaultdict(list)
for c in dummy_cols:
    field_cols[col_field[c]].append(c)
nfields = np.zeros(N)
for f, cols in field_cols.items():
    idx = [pos[c] for c in cols]
    nfields += (P[:, idx].sum(axis=1) > 0).astype(float)
nvalues = P.sum(axis=1)

# ------------------------------------------------------ helpers ---------------
def correlation_ratio(labels, y):
    """eta^2: fraction of variance in y explained by cluster membership."""
    y = np.asarray(y, float); mu = y.mean()
    ssb = sum(len(y[labels == g]) * (y[labels == g].mean() - mu) ** 2 for g in np.unique(labels))
    sst = ((y - mu) ** 2).sum()
    return ssb / sst if sst > 0 else 0.0

def l2norm(M):
    n = np.linalg.norm(M, axis=1, keepdims=True); n[n == 0] = 1.0
    return M / n

def residualize(M, x):
    """Regress every column on x (centered) and keep residuals — removes the x axis."""
    M = M - M.mean(0); xc = np.asarray(x, float) - np.mean(x)
    d = (xc ** 2).sum()
    if d == 0:
        return M
    beta = (M * xc[:, None]).sum(0) / d
    return M - np.outer(xc, beta)

def diagnose(M, label):
    pca = PCA(n_components=min(PCS, M.shape[1]), random_state=SEED)
    Z = pca.fit_transform(M - M.mean(0))
    pc1 = Z[:, 0]
    pear = pearsonr(pc1, nfields)[0]
    spear = spearmanr(pc1, nfields)[0]
    sils = {}
    for k in KRANGE:
        km = KMeans(n_clusters=k, n_init=10, random_state=SEED).fit(Z)
        sils[k] = silhouette_score(Z, km.labels_)
    best_k = max(sils, key=sils.get)
    labels = KMeans(n_clusters=best_k, n_init=10, random_state=SEED).fit(Z).labels_
    eta2 = correlation_ratio(labels, nfields)
    return dict(label=label, pear=pear, spear=spear, var1=pca.explained_variance_ratio_[0],
                sils=sils, best_k=best_k, best_sil=sils[best_k], eta2=eta2, labels=labels, Z=Z)

# ------------------------------------------ Step 0.5: condition validation ----
con = sqlite3.connect(str(DB))
varrows = list(con.execute("select user_id, field, value from variables"))
con.close()

def members(canon_pat, field="conditions"):
    """raw condition values (with patient counts) that match a canonical pattern."""
    cnt = defaultdict(int)
    for uid, f, v in varrows:
        if f != field:
            continue
        for piece in (v or "").split(" | "):
            p = piece.strip().lower()
            if p and re.search(canon_pat, p):
                cnt[p] += 1
    return dict(sorted(cnt.items(), key=lambda x: -x[1]))

def patients_with(pat, fields):
    s = set()
    for uid, f, v in varrows:
        if f in fields and re.search(pat, (v or "").lower()):
            s.add(str(uid))
    return s

me_members = members(r"me/?cfs|myalgic|chronic fatigue")
ms_members = members(r"^ms$|multiple sclerosis")
EDS = r"ehlers|hypermob|\beds\b|heds|\bcci\b|\bhsd\b"
eds_cond = patients_with(EDS, {"conditions"})
eds_ctis = patients_with(EDS, {"connective_tissue_symptoms"})
eds_any = eds_cond | eds_ctis
eds_any_vec = np.array([1.0 if i in eds_any else 0.0 for i in ids])

# ------------------------------------------------ representations --------------
analysis_cols = [c for c in dummy_cols if str(fd.get(col_field[c], {}).get("analysis_grade")) == "yes"]
A_idx = [pos[c] for c in analysis_cols]
P_A = P[:, A_idx]
w = np.array([math.log((1 + N) / (1 + col_df[c])) + 1 for c in analysis_cols])   # IDF

reps = [
    diagnose(P,                      "raw presence (all dummies)"),
    diagnose(P_A,                    "A: analysis-grade fields only"),
    diagnose(P_A * w,                "A+IDF: inverse-prevalence weighted"),
    diagnose(l2norm(P_A * w),        "A+IDF+L2 (cosine)  <-- controlled"),
]
controlled = reps[-1]
# gate: residualize only if cosine still tracks verbosity
resid_rep = None
if abs(controlled["pear"]) > 0.30:
    resid_rep = diagnose(residualize(l2norm(P_A * w), nfields), "A+IDF+L2+residualized n_fields")
    reps.append(resid_rep)

# ----------------------------------------- cluster coherence (markers) --------
final = resid_rep or controlled
labels = final["labels"]
# marker indicators: matrix dummies for these + corrected eds_any
markers = {}
for canon in ["pots", "mcas", "me_cfs", "dysautonomia", "small_fiber_neuropathy", "fibromyalgia"]:
    col = f"conditions={canon}"
    markers[canon] = P[:, pos[col]] if col in pos else np.zeros(N)
markers["eds_any"] = eds_any_vec

def profiles(labels, M_presence, cols, topn=8):
    overall = M_presence.mean(0)
    out = {}
    for g in sorted(np.unique(labels)):
        sel = labels == g
        m = M_presence[sel].mean(0)
        lift = m / (overall + 1e-9)
        cand = sorted([(cols[j], m[j], lift[j]) for j in range(len(cols)) if m[j] >= 0.05],
                      key=lambda t: -t[2])[:topn]
        out[g] = (int(sel.sum()), cand)
    return out

prof = profiles(labels, P_A, analysis_cols)

# ----------------------------------------------------- figures ----------------
def scatter(rep, fname, title):
    Z = rep["Z"]
    plt.figure(figsize=(7, 5.5))
    sc = plt.scatter(Z[:, 0], Z[:, 1], c=nfields, s=6, cmap="viridis", alpha=0.6)
    plt.colorbar(sc, label="n_fields_filled (verbosity)")
    plt.xlabel("PC1"); plt.ylabel("PC2")
    plt.title(f"{title}\nPC1~verbosity r={rep['pear']:+.2f}")
    plt.tight_layout(); plt.savefig(FIG / fname, dpi=110); plt.close()

scatter(reps[0], "pca_verbosity_before.png", "BEFORE — raw presence")
scatter(final, "pca_verbosity_after.png", "AFTER — " + final["label"])

# ----------------------------------------------------- report -----------------
lines = []
def w_(s=""):
    lines.append(s); print(s)

w_(f"VERBOSITY-CONFOUND CONTROL  |  {N} patients  |  {len(dummy_cols)} dummies, "
   f"{len(analysis_cols)} analysis-grade")
w_(f"verbosity: n_fields_filled mean={nfields.mean():.1f} (min {int(nfields.min())}, "
   f"max {int(nfields.max())});  n_values mean={nvalues.mean():.1f}")
w_("")
w_("== Step 0.5  condition canonicalization (re: Eli's me_cfs / ms / eds flags) ==")
w_(f"  me_cfs <= {me_members}  (no substring 'me' false positives; exact/guarded matching)")
w_(f"     note: 'chronic fatigue'(symptom) maps into me_cfs for {me_members.get('chronic fatigue',0)} "
   f"patients — minor over-merge (symptom != ME/CFS diagnosis); split if strict.")
w_(f"  ms     <= {ms_members}  ('ms'=Mississippi correctly lands in location_us_state, not conditions)")
w_(f"  eds    conditions={len(eds_cond)}  connective_tissue_only={len(eds_ctis - eds_cond)}  "
   f"=> eds_any={len(eds_any)}  (the real undercount: +{len(eds_any)-len(eds_cond)} via cross-field)")
w_("  -> me_cfs & ms valid as-is; use eds_any (not conditions=eds) for EDS. Others "
   "(mcas/dysautonomia/sfn) already complete in conditions.")
w_("")
w_("== before/after diagnostics ==")
hdr = f"  {'representation':<34} {'PC1~nfields':>16} {'PC1var':>7} {'bestk':>6} {'silhou':>7} {'verb_eta2':>9}"
w_(hdr); w_("  " + "-" * (len(hdr) - 2))
for r in reps:
    w_(f"  {r['label']:<34} {r['pear']:+.2f}/{r['spear']:+.2f}   {r['var1']*100:5.1f}% "
       f"{r['best_k']:>5} {r['best_sil']:>7.2f} {r['eta2']:>9.2f}")
w_("")
w_("  PC1~nfields = corr of 1st PC with verbosity (want -> 0).  verb_eta2 = share of n_fields")
w_("  variance explained by cluster labels (want -> 0: clusters NOT sorted by verbosity).")
w_("")
b, a = reps[0], final
w_(f"  HEADLINE: |PC1~nfields| {abs(b['pear']):.2f} -> {abs(a['pear']):.2f}   |   "
   f"verb_eta2 {b['eta2']:.2f} -> {a['eta2']:.2f}")
w_(f"  residualization {'WAS' if resid_rep else 'was NOT'} needed "
   f"(cosine PC1~nfields = {controlled['pear']:+.2f}).")
w_("  CAVEAT: n_fields partly encodes real illness burden (sicker patients report more) — we")
w_("  control it, not erase it; residualization is the last resort and can strip severity signal.")
w_("")
w_(f"== cluster profiles ({final['label']}, k={final['best_k']}) — top features by lift ==")
for g, (n, cand) in prof.items():
    w_(f"  cluster {g}  (n={n})")
    for name, mean, lift in cand:
        w_(f"      {lift:4.1f}x  {mean*100:4.0f}%  {name}")
    # marker prevalence in this cluster
    sel = labels == g
    mk = "  ".join(f"{k}={markers[k][sel].mean()*100:.0f}%" for k in markers)
    w_(f"      markers: {mk}")
w_("")

# ------------------------------------------------ write artifacts --------------
(CLEAN / "verbosity_report.txt").write_text("\n".join(lines), encoding="utf-8")

ctrl = l2norm(P_A * w)
out = pd.DataFrame(ctrl, columns=analysis_cols)
out.insert(0, "eds_any", eds_any_vec)
out.insert(0, "n_values", nvalues)
out.insert(0, "n_fields_filled", nfields)
out.insert(0, KEY, ids)
out.to_csv(CLEAN / "model_matrix_controlled.csv", index=False)

print(f"\nwrote: data/clean/verbosity_report.txt")
print(f"wrote: data/clean/model_matrix_controlled.csv  ({out.shape[0]} x {out.shape[1]})")
print(f"wrote: data/clean/figures/pca_verbosity_before.png, pca_verbosity_after.png")
