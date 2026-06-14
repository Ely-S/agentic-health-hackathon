#!/usr/bin/env python3
"""
treatment_pooled_model.py — pooled, partially-pooled model of treatment-effect heterogeneity.

One logistic over ALL pos/neg reports:
    P(positive) ~ drug_group + condition + drug_group x condition + severity covariates
The drug_group x condition INTERACTIONS are the heterogeneity (does a drug's help-rate depend
on the part of the spectrum). L2 penalty = partial pooling (each drug's per-condition deviation
is shrunk toward the global condition effect). CIs by PATIENT bootstrap (a patient contributes
many reports -> must resample patients, not rows). Drug groups are broad mechanism classes
(power over granularity, by request).

Outputs (data/clean/): treatment_pooled_report.txt, figures/treatment_pooled_heatmap.png.
Observational, reporting-biased, NOT causal.
"""
from __future__ import annotations
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import seaborn as sns
warnings.simplefilter("ignore")

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
KEY = "author_hash"
B = 250           # bootstrap resamples
C_REG = 1.0       # inverse L2 strength (partial pooling)
SEED = 0

# ---- patients: conditions + severity covariates ------------------------------
ctrl = pd.read_csv(CLEAN / "model_matrix_controlled.csv")
man = pd.read_csv(CLEAN / "column_manifest.csv")
full = pd.read_csv(CLEAN / "model_matrix.csv").set_index(KEY)
CONDS = ["pots", "mcas", "dysautonomia", "me_cfs", "pem", "small_fiber_neuropathy", "fibromyalgia", "eds_any"]
pt = pd.DataFrame({KEY: ctrl[KEY]})
for c in CONDS[:-1]:
    col = f"conditions={c}"
    pt[c] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
pt["eds_any"] = ctrl["eds_any"].to_numpy()
# severity / verbosity covariates
pt["nfields_z"] = (ctrl["n_fields_filled"] - ctrl["n_fields_filled"].mean()) / ctrl["n_fields_filled"].std()
COVARS = ["nfields_z"]
for col in full.columns:
    fld = man.loc[man.column == col, "field"]
    if col.startswith("functional_status_tier=") or col.startswith("symptom_trajectory="):
        pt[col] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy()
        COVARS.append(col)
pt = pt.set_index(KEY)

# ---- drug sentiment -> broad mechanism groups (priority order) ---------------
ds = pd.read_csv(CLEAN.parent / "csv_export" / "drug_sentiment.csv")
ds = ds[ds.sentiment.isin(["positive", "negative"])].copy()
ds["d"] = ds.drug.astype(str).str.lower()
GROUPS = {  # first match wins
    "antihistamine/mast-cell": r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b",
    "autonomic/cardiovascular": r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression",
    "neuro-psychiatric": r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin",
    "LDN/immunomodulator": r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine|colchicine",
    "antiviral/anticoagulant": r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir|nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban",
    "supplement/mitochondrial": r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose",
    "metabolic": r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|low.?dose.*lithium",
}
def group_of(d):
    for g, pat in GROUPS.items():
        if pd.Series([d]).str.contains(pat, regex=True)[0]:
            return g
    return None
ds["group"] = ds["d"].map(group_of)
ds = ds[ds.group.notna()].copy()
ds = ds.join(pt, on="user_id")
ds = ds.dropna(subset=CONDS + COVARS)
ds["y"] = (ds.sentiment == "positive").astype(int)
GLIST = list(GROUPS)  # ref = GLIST[0]

# ---- design matrix -----------------------------------------------------------
DCOLS = ([f"drug={g}" for g in GLIST[1:]]
         + [f"cond={c}" for c in CONDS]
         + [f"drug={g}:cond={c}" for g in GLIST[1:] for c in CONDS]
         + COVARS)

def design(df):
    X = np.zeros((len(df), len(DCOLS)))
    gi = {c: k for k, c in enumerate(DCOLS)}
    grp = df["group"].to_numpy()
    cond = {c: df[c].to_numpy() for c in CONDS}
    for g in GLIST[1:]:
        isg = (grp == g).astype(float)
        X[:, gi[f"drug={g}"]] = isg
        for c in CONDS:
            X[:, gi[f"drug={g}:cond={c}"]] = isg * cond[c]
    for c in CONDS:
        X[:, gi[f"cond={c}"]] = cond[c]
    for cv in COVARS:
        X[:, gi[cv]] = df[cv].to_numpy()
    return X

X = design(ds); y = ds["y"].to_numpy()
def fit(Xm, ym):
    return LogisticRegression(penalty="l2", C=C_REG, max_iter=3000, solver="lbfgs").fit(Xm, ym)
base = fit(X, y)
coef = dict(zip(DCOLS, base.coef_[0]))

# predicted P(positive): row = drug group g with only condition c (covars at mean)
covar_mean = ds[COVARS].mean().to_dict()
def pred_row(g, c):
    r = {k: 0.0 for k in DCOLS}
    for cv in COVARS:
        r[cv] = covar_mean[cv]
    if g != GLIST[0]:
        r[f"drug={g}"] = 1.0
        if c:
            r[f"drug={g}:cond={c}"] = 1.0
    if c:
        r[f"cond={c}"] = 1.0
    return np.array([r[k] for k in DCOLS])
def predict(model, g, c):
    return model.predict_proba(pred_row(g, c).reshape(1, -1))[0, 1]

# ---- patient bootstrap -------------------------------------------------------
rng = np.random.default_rng(SEED)
pat_ids = ds["user_id"].to_numpy()
uniq = np.unique(pat_ids)
rows_by_pat = {p: np.where(pat_ids == p)[0] for p in uniq}
inter_boot = {(g, c): [] for g in GLIST[1:] for c in CONDS}
pred_boot = {(g, c): [] for g in GLIST for c in [None] + CONDS}
for b in range(B):
    samp = rng.choice(uniq, size=len(uniq), replace=True)
    idx = np.concatenate([rows_by_pat[p] for p in samp])
    try:
        m = fit(X[idx], y[idx])
    except Exception:
        continue
    cb = dict(zip(DCOLS, m.coef_[0]))
    for g in GLIST[1:]:
        for c in CONDS:
            inter_boot[(g, c)].append(cb[f"drug={g}:cond={c}"])
    for g in GLIST:
        for c in [None] + CONDS:
            pred_boot[(g, c)].append(predict(m, g, c))

def ci(v):
    a = np.array(v)
    return (np.percentile(a, 2.5), np.percentile(a, 97.5)) if len(a) else (np.nan, np.nan)

# ---- report ------------------------------------------------------------------
report = []
def W(s=""):
    report.append(s); print(s)

W("POOLED PARTIALLY-POOLED MODEL — treatment-effect heterogeneity")
W(f"  {len(ds)} pos/neg reports | {len(uniq)} patients | overall positive {y.mean()*100:.0f}%")
W(f"  groups (n reports): " + ", ".join(f"{g}={int((ds.group==g).sum())}" for g in GLIST))
W(f"  model: P(pos) ~ drug_group*condition + severity covars; L2 C={C_REG}; {B} patient-bootstraps")
W(f"  ref drug group = '{GLIST[0]}'; covariates = {COVARS}\n")

W("== drug_group x condition INTERACTIONS (heterogeneity; OR>1 better, <1 worse for that part) ==")
sig = []
for g in GLIST[1:]:
    for c in CONDS:
        if not inter_boot[(g, c)]:
            continue
        orr = np.exp(np.median(inter_boot[(g, c)]))
        lo, hi = np.exp(ci(inter_boot[(g, c)]))
        if lo > 1 or hi < 1:
            sig.append((abs(np.log(orr)), g, c, orr, lo, hi))
for _, g, c, orr, lo, hi in sorted(sig, reverse=True):
    arrow = "BETTER" if orr > 1 else "WORSE "
    W(f"   {arrow}  OR={orr:4.2f} [{lo:4.2f},{hi:5.2f}]   {g:<26} x {c}")
if not sig:
    W("   (no interaction CI excludes 1 at this pooling strength)")
W("   ^ interactions whose 95% bootstrap CI excludes 1 (full-data powered, partially pooled).\n")

W("== predicted P(positive) by drug group x condition (model-smoothed; baseline=no marker) ==")
hdr = "  " + "drug group".ljust(28) + "baseln " + " ".join(c[:6].rjust(7) for c in CONDS)
W(hdr)
H = pd.DataFrame(index=GLIST, columns=["baseline"] + CONDS, dtype=float)
for g in GLIST:
    H.loc[g, "baseline"] = np.median(pred_boot[(g, None)]) * 100
    cells = []
    for c in CONDS:
        p = np.median(pred_boot[(g, c)]) * 100
        H.loc[g, c] = p
        lo, hi = ci(pred_boot[(g, c)])
        mark = "*" if (g != GLIST[0] and (np.exp(ci(inter_boot[(g, c)])[0]) > 1 or np.exp(ci(inter_boot[(g, c)])[1]) < 1)) else " "
        cells.append(f"{p:5.0f}{mark}")
    W("  " + g.ljust(28) + f"{H.loc[g,'baseline']:5.0f}  " + " ".join(x.rjust(7) for x in cells))
W("  * = the group x condition interaction CI excludes 1 (real deviation). Cells are % positive.\n")

W("  CAVEATS: observational self-report (~80% positive ceiling); broad drug groups blend distinct")
W("  drugs (e.g. magnesium vs CoQ10) so within-group effects are masked; conditions overlap;")
W("  selection bias uncontrolled. Hypothesis-generating, NOT causal/efficacy.")
(CLEAN / "treatment_pooled_report.txt").write_text("\n".join(report), encoding="utf-8")

# ---- heatmap -----------------------------------------------------------------
plt.figure(figsize=(11, 6))
ann = H.copy().round(0).astype(int).astype(str)
sns.heatmap(H.astype(float), annot=ann.values, fmt="", cmap="RdYlGn", center=80, vmin=50, vmax=100,
            linewidths=.5, cbar_kws={"label": "model P(positive) %"})
plt.title("Pooled model: predicted positive-response rate by drug group x condition\n"
          "(partially pooled; baseline col = no marker condition)")
plt.tight_layout()
plt.savefig(CLEAN / "figures" / "treatment_pooled_heatmap.png", dpi=120)
plt.close()
print("\nwrote: data/clean/treatment_pooled_report.txt + figures/treatment_pooled_heatmap.png")
