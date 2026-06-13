#!/usr/bin/env python3
"""
treatment_spectrum_models.py — does the spectrum predict whether a treatment helps OR harms?

Part A (reverse / CONTRAINDICATION descriptive): which conditions RAISE a drug class's harm
  rate (negative reports / all mentions)? Fisher + BH-FDR.
Part B (per-drug adjusted LOGIT): logit(P(positive vs negative) ~ conditions + symptoms),
  statsmodels, parsimonious (cap ~events/8) + separation-guarded -> adjusted odds ratios.
  OR>1 = indicative, OR<1 = counterindicative, holding other predictors fixed.

Observational self-report, ~78% positive ceiling, conditions overlap heavily, negatives scarce
(=> power-limited). Hypothesis-generating, NOT causal / efficacy.
Reads data/clean/* + data/csv_export/drug_sentiment.csv. Writes a report. Read-only on inputs.
"""
from __future__ import annotations
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import fisher_exact
import statsmodels.api as sm
warnings.simplefilter("ignore")

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
KEY = "author_hash"

# ---- patients: marker conditions + broad (conditions+symptoms) predictor pool ----
ctrl = pd.read_csv(CLEAN / "model_matrix_controlled.csv")
man = pd.read_csv(CLEAN / "column_manifest.csv")
full = pd.read_csv(CLEAN / "model_matrix.csv").set_index(KEY)
CONDS = ["pots", "mcas", "dysautonomia", "me_cfs", "pem", "small_fiber_neuropathy", "fibromyalgia"]
mk = pd.DataFrame({KEY: ctrl[KEY]})
for c in CONDS:
    col = f"conditions={c}"
    mk[c] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
mk["eds_any"] = ctrl["eds_any"].to_numpy()
CONDS = CONDS + ["eds_any"]
mk = mk.set_index(KEY)

# predictor pool = phenotype/experience/biomarker/demographic dummies (conditions AND symptoms;
# excludes treatment fields = circular, and treatment_outcome = leaky)
pred_cats = {"phenotype", "experience", "biomarker", "demographic"}
pred_cols = [r["column"] for _, r in man.iterrows()
             if r["type"] == "dummy" and r["field_category"] in pred_cats and r["column"] in full.columns]
X_all = full[pred_cols].reindex(ctrl[KEY]).fillna(0)
X_all.index = ctrl[KEY].values
X_all["eds_any"] = ctrl["eds_any"].to_numpy()
pred_cols = pred_cols + ["eds_any"]

# ---- drug sentiment -> clinical classes ----
ds = pd.read_csv(CLEAN.parent / "csv_export" / "drug_sentiment.csv")
ds = ds[ds.sentiment.isin(["positive", "negative", "mixed"])].copy()
ds["d"] = ds.drug.astype(str).str.lower()
CLASSES = {
    "LDN (naltrexone)": r"naltrexone|ldn",
    "antihistamine (H1/H2)": r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|\bh1\b|\bh2\b",
    "mast-cell stabilizer": r"cromolyn|ketotifen|quercetin|mast cell",
    "beta blocker": r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol",
    "ivabradine": r"ivabradine|corlanor",
    "POTS volume (salt/fludro/midodrine)": r"midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression",
    "SSRI/SNRI": r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta",
    "metformin": r"metformin",
    "paxlovid/antiviral": r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir",
    "anticoagulant/nattokinase": r"nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban",
    "magnesium": r"magnesium",
    "CoQ10/mito": r"coq10|coenzyme|ubiquinol",
    "B12/B-complex": r"\bb12\b|b-12|methylcobalamin|b complex|b-complex|b vitamin",
    "vitamin D": r"vitamin d|\bvit d\b",
    "LDA (low-dose abilify)": r"abilify|aripiprazole",
}
ds = ds.join(mk, on="user_id")
for c in CONDS:
    ds[c] = ds[c].fillna(0).astype(int)
ds["pos"] = (ds.sentiment == "positive").astype(int)
ds["neg"] = (ds.sentiment == "negative").astype(int)

def bh(p):
    p = np.asarray(p, float); n = len(p); o = np.argsort(p); q = np.empty(n); prev = 1.0
    for r, i in enumerate(reversed(o)):
        k = n - r; prev = min(prev, p[i] * n / k); q[i] = prev
    return q

report = []
def W(s=""):
    report.append(s); print(s)

# ===================== PART A: contraindication (harm) descriptive ====================
W("PART A - CONTRAINDICATION (harm) DESCRIPTIVE: negative-report rate by condition")
W("  harm rate = negatives / all mentions; Fisher [neg vs not] x [with vs without]; BH-FDR\n")
rows = []
for cls, pat in CLASSES.items():
    sub = ds[ds.d.str.contains(pat, regex=True, na=False)]
    if len(sub) < 40:
        continue
    for c in CONDS:
        w_, o_ = sub[sub[c] == 1], sub[sub[c] == 0]
        if len(w_) < 10 or len(o_) < 10:
            continue
        _, p = fisher_exact([[int(w_.neg.sum()), len(w_) - int(w_.neg.sum())],
                             [int(o_.neg.sum()), len(o_) - int(o_.neg.sum())]])
        rows.append(dict(cls=cls, cond=c, hw=w_.neg.mean(), ho=o_.neg.mean(),
                         delta=w_.neg.mean() - o_.neg.mean(), n=len(w_), p=p))
A = pd.DataFrame(rows); A["q"] = bh(A.p); A = A.sort_values("delta", ascending=False)
W(f"  {'drug class':<34}{'condition':<14}{'harm_with':>11}{'without':>9}{'delta':>8}{'q':>8}")
W("  " + "-" * 84)
for _, r in A.head(16).iterrows():
    star = "*" if r.q < 0.10 else " "
    W(f" {star}{r.cls:<34}{r.cond:<14}{r.hw*100:5.0f}% (n{r.n:<3}){r.ho*100:5.0f}% {r.delta*100:+6.0f}pp {r.q:7.3f}")
W("  (top rows = conditions that most RAISE a class's harm rate = contraindication signal)\n")

# ===================== PART B: per-drug adjusted logit ================================
W("PART B - PER-DRUG ADJUSTED LOGIT: P(positive vs negative) ~ conditions + symptoms")
W("  adjusted OR>1 indicative, OR<1 counterindicative; parsimonious (cap ~events/8), sep-guarded\n")

def fit_drug(cls, pat):
    sub = ds[ds.d.str.contains(pat, regex=True, na=False)]
    sub = sub[sub.sentiment.isin(["positive", "negative"])].drop_duplicates(["user_id"])
    n = len(sub)
    if n < 60:
        return None
    y = sub.pos.values
    ev = int(min(y.sum(), n - y.sum()))
    if ev < 12:
        return (cls, n, ev, None)
    X = X_all.reindex(sub.user_id).fillna(0).reset_index(drop=True)
    keep = []
    for col in pred_cols:
        v = X[col].values; s = v.sum()
        if s < max(6, 0.08 * n) or s > n - max(6, 0.08 * n):
            continue
        if y[v == 1].sum() in (0, int((v == 1).sum())) or y[v == 0].sum() in (0, int((v == 0).sum())):
            continue
        keep.append(col)
    if not keep:
        return (cls, n, ev, None)
    corr = {col: abs(np.corrcoef(X[col].values, y)[0, 1]) for col in keep}
    sel = [c for c, _ in sorted(corr.items(), key=lambda t: -t[1])[:max(2, ev // 8)]]
    try:
        m = sm.Logit(y, sm.add_constant(X[sel].astype(float))).fit(disp=0, maxiter=100)
        ci = m.conf_int()
    except Exception:
        return (cls, n, ev, None)
    out = [dict(cls=cls, pred=col, OR=np.exp(m.params[col]), lo=np.exp(ci.loc[col, 0]),
                hi=np.exp(ci.loc[col, 1]), p=m.pvalues[col]) for col in sel]
    return (cls, n, ev, out)

allrows = []
for cls, pat in CLASSES.items():
    r = fit_drug(cls, pat)
    if r is None:
        continue
    cls_, n, ev, out = r
    if out is None:
        W(f"  {cls_:<34} n={n} minority_events={ev}  -> underpowered / no stable predictors")
        continue
    W(f"  {cls_}  (n={n}, minority events={ev})")
    for o in sorted(out, key=lambda x: x["OR"]):
        sig = "*" if o["p"] < 0.05 else " "
        tag = "COUNTERindicative" if o["OR"] < 1 else "indicative"
        W(f"    {sig}OR={o['OR']:4.2f} [{o['lo']:4.2f},{o['hi']:5.2f}] p={o['p']:.3f}  {o['pred']:<34}{tag}")
        allrows.append({**o, "n": n})
    W("")

W("  * p<0.05 (selection-optimistic: predictors picked by univariate signal -> exploratory).")
W("  CAVEATS: scarce negatives => few predictors/drug; conditions overlap; reporting+selection")
W("  bias; observational, NOT causal/efficacy.")

(CLEAN / "treatment_spectrum_models_report.txt").write_text("\n".join(report), encoding="utf-8")
print("\nwrote: data/clean/treatment_spectrum_models_report.txt")
