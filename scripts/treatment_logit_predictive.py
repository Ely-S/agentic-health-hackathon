#!/usr/bin/env python3
"""
treatment_logit_predictive.py — per-drug logit models: what conditions/symptoms predict
SUCCESS vs FAILURE for each (widened) drug group?

For each broad drug group: logit(P(positive vs negative)) ~ conditions + symptoms (a priori
clinical predictor set, prevalence-filtered, separation-guarded). Reports each predictor's
odds ratio (OR>1 -> predicts success, OR<1 -> predicts failure) with CI + p, and saves the
coefficients so the model can score a new patient. statsmodels Logit.

Groups widened (priority order, first match wins) to cover more of the report volume.
Observational, ~80% positive ceiling, conditions overlap -> hypothesis-generating, not causal.
Reads data/clean/* + data/patientpunk.db. Writes report + coefficient CSV to data/clean/.
"""
from __future__ import annotations
import re, warnings
from pathlib import Path
import numpy as np
import pandas as pd
import statsmodels.api as sm
warnings.simplefilter("ignore")

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
KEY = "author_hash"

# ---- predictors: conditions + symptoms (a priori, clinical) ------------------
ctrl = pd.read_csv(CLEAN / "model_matrix_controlled.csv")
full = pd.read_csv(CLEAN / "model_matrix.csv").set_index(KEY)
CONDS = ["pots", "mcas", "dysautonomia", "me_cfs", "pem", "small_fiber_neuropathy", "fibromyalgia"]
P = pd.DataFrame(index=ctrl[KEY])
for c in CONDS:
    col = f"conditions={c}"
    P[c] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
P["eds_any"] = ctrl["eds_any"].to_numpy()
PREDS = CONDS + ["eds_any"]
for col in full.columns:                       # cleaned symptom predictors
    if col.startswith("symptom_trajectory=") or col.startswith("functional_status_tier="):
        name = col.replace("symptom_trajectory=", "traj_").replace("functional_status_tier=", "func_").replace(" ", "_")
        P[name] = full[col].reindex(ctrl[KEY]).fillna(0).to_numpy()
        PREDS.append(name)
P["nfields_z"] = ((ctrl["n_fields_filled"] - ctrl["n_fields_filled"].mean()) / ctrl["n_fields_filled"].std()).to_numpy()
PREDS.append("nfields_z")
COND_SET = set(CONDS + ["eds_any"])

# ---- drug sentiment -> widened mechanism groups (priority order) -------------
ds = pd.read_csv(CLEAN.parent / "csv_export" / "drug_sentiment.csv")
ds = ds[ds.sentiment.isin(["positive", "negative"])].copy()
ds["d"] = ds.drug.astype(str).str.lower()
GROUPS = {
    "antihistamine/mast-cell": r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b|nasal spray",
    "autonomic/cardiovascular": r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression|guanfacine|clonidine|pyridostigmine|mestinon",
    "neuro-psychiatric": r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin|selective serotonin|antidepressant|xanax|fluvoxamine|mirtazapine|amitriptyline|nortriptyline",
    "LDN/immunomodulator": r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine|colchicine",
    "antiviral/anticoagulant": r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir|nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban|lumbrokinase|maraviroc",
    "supplement/mitochondrial": r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|cannabidiol|\bcbd\b|alpha.?lipoic",
    "peptide/experimental": r"bpc.?157|ss.?31|thymosin|peptide|rapamycin|sirolimus",
    "metabolic": r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro|low.?dose.*lithium",
    "procedure/device": r"nicotine|hyperbaric|\bhbot\b|stellate ganglion|acupuncture|vagus|red light|\bvaccine\b",
}
def group_of(d):
    for g, pat in GROUPS.items():
        if re.search(pat, d):
            return g
    return None
ds["group"] = ds["d"].map(group_of)
ds = ds.join(P, on="user_id").dropna(subset=PREDS)
ds["y"] = (ds.sentiment == "positive").astype(int)

report, coefrows = [], []
def W(s=""):
    report.append(s); print(s)

cov = int(ds.group.notna().sum())
W("PER-DRUG PREDICTIVE LOGIT — what conditions/symptoms predict SUCCESS vs FAILURE")
W(f"  widened groups cover {cov}/{len(ds)} pos+neg reports ({100*cov//len(ds)}%); overall positive {ds.y.mean()*100:.0f}%\n")

def fit_group(g):
    sub = ds[ds.group == g].drop_duplicates("user_id")
    n = len(sub); y = sub.y.values; ev = int(min(y.sum(), n - y.sum()))
    if n < 120 or ev < 30:
        return n, ev, None
    # prevalence-filter predictors that can be estimated in this group
    ok = []
    for p in PREDS:
        v = sub[p].values
        if p == "nfields_z":
            ok.append(p); continue
        s = v.sum()
        if s < max(8, 0.05 * n) or s > n - max(8, 0.05 * n):
            continue
        if y[v == 1].sum() in (0, int((v == 1).sum())) or y[v == 0].sum() in (0, int((v == 0).sum())):
            continue
        ok.append(p)
    # budget by events; conditions get priority (they are the question)
    budget = max(4, ev // 8)
    conds = [p for p in ok if p in COND_SET]
    syms = [p for p in ok if p not in COND_SET]
    sel = (conds + syms)[:budget] if len(conds) <= budget else \
        sorted(conds, key=lambda p: -sub[p].sum())[:budget]
    # fit with separation/convergence retry
    for _ in range(len(sel)):
        try:
            m = sm.Logit(y, sm.add_constant(sub[sel].astype(float))).fit(disp=0, maxiter=200)
            if np.isfinite(m.bse).all() and (np.abs(m.params) < 12).all():
                return n, ev, (sub, m, sel)
        except Exception:
            pass
        # drop the most extreme coefficient and retry
        try:
            worst = m.params.drop("const").abs().idxmax(); sel = [s for s in sel if s != worst]
        except Exception:
            break
        if not sel:
            break
    return n, ev, None

for g in GROUPS:
    n, ev, res = fit_group(g)
    if res is None:
        W(f"  {g:<28} n={n} events={ev}  -> underpowered / unstable"); continue
    sub, m, sel = res
    ci = m.conf_int()
    W(f"  {g}  (n={n}, minority events={ev})")
    rowinfo = [(p, np.exp(m.params[p]), np.exp(ci.loc[p, 0]), np.exp(ci.loc[p, 1]), m.pvalues[p]) for p in sel]
    for p, orr, lo, hi, pv in sorted(rowinfo, key=lambda x: x[1]):
        sig = "*" if pv < 0.05 else " "
        tag = "predicts FAILURE" if orr < 1 else "predicts success"
        kind = "cond" if p in COND_SET else "symp"
        W(f"    {sig}OR={orr:5.2f} [{lo:4.2f},{hi:6.2f}] p={pv:.3f}  {kind} {p:<26}{tag if pv < 0.05 else ''}")
        coefrows.append(dict(group=g, predictor=p, OR=orr, ci_lo=lo, ci_hi=hi, p=pv,
                             coef=m.params[p], n=n))
    coefrows.append(dict(group=g, predictor="const", OR=np.nan, ci_lo=np.nan, ci_hi=np.nan,
                         p=np.nan, coef=m.params["const"], n=n))
    W("")

W("  * p<0.05. OR<1 => that condition/symptom predicts the drug FAILING for the patient.")
W("  Predictors are an a-priori clinical set (no data-snooping). Conditions overlap; observational;")
W("  ~80% positive ceiling => failure predictors are the higher-signal output. Coefficients saved")
W("  to drug_logit_coefficients.csv for scoring a new patient (logit = const + sum coef*predictor).")

(CLEAN / "treatment_logit_predictive_report.txt").write_text("\n".join(report), encoding="utf-8")
pd.DataFrame(coefrows).to_csv(CLEAN / "drug_logit_coefficients.csv", index=False)
print("\nwrote: data/clean/treatment_logit_predictive_report.txt + drug_logit_coefficients.csv")
