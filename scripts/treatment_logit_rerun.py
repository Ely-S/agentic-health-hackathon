#!/usr/bin/env python3
"""
treatment_logit_rerun.py — per-drug-category logit models on the RE-RUN (corrected) sentiment.

One logit per drug category: P(helped) ~ conditions + severity.
  outcome: success = `positive`; failure = `negative` OR `no_effect`; `mixed` dropped.
  predictors (a-priori, no univariate selection): 8 marker conditions + functional-severity
             + n_fields (severity proxy). symptom_trajectory is EXCLUDED (outcome-adjacent).
statsmodels Logit, prevalence-filtered + events-capped + separation-guarded. Saves coefficients
for scoring. Reports each estimable category and flags the underpowered ones.

Reads re-run sentiment from pp_rebase/posts_rerun.db + patient features from data/clean/.
Writes data/clean/drug_logit_rerun_report.txt + drug_logit_coefficients_rerun.csv.
"""
from __future__ import annotations
import re, sqlite3, warnings
from pathlib import Path
import numpy as np, pandas as pd
import statsmodels.api as sm
warnings.simplefilter("ignore")

ROOT = Path(__file__).resolve().parents[1]; CLEAN = ROOT/"data"/"clean"; KEY="author_hash"
RERUN_DB = Path("C:/Users/scgee/Downloads/pp_rebase/posts_rerun.db")

# ---- patient predictors: conditions + severity (NO trajectory) ----
ctrl = pd.read_csv(CLEAN/"model_matrix_controlled.csv")
full = pd.read_csv(CLEAN/"model_matrix.csv").set_index(KEY)
CONDS = ["pots","mcas","dysautonomia","me_cfs","pem","small_fiber_neuropathy","fibromyalgia"]
P = pd.DataFrame(index=ctrl[KEY])
for c in CONDS:
    col=f"conditions={c}"; P[c]= full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
P["eds_any"]=ctrl["eds_any"].to_numpy()
PREDS = CONDS+["eds_any"]
for sev in ["functional_status_tier=severe","functional_status_tier=housebound","functional_status_tier=bedbound","functional_status_tier=mobility_limited"]:
    if sev in full.columns:
        nm=sev.replace("functional_status_tier=","func_"); P[nm]=full[sev].reindex(ctrl[KEY]).fillna(0).to_numpy(); PREDS.append(nm)
P["nfields_z"]=((ctrl["n_fields_filled"]-ctrl["n_fields_filled"].mean())/ctrl["n_fields_filled"].std()).to_numpy()
PREDS.append("nfields_z"); COND_SET=set(CONDS+["eds_any"])

# ---- re-run sentiment -> success/failure ----
con=sqlite3.connect(str(RERUN_DB))
ds=pd.read_sql("select tr.user_id, t.canonical_name as drug, tr.sentiment from treatment_reports tr join treatment t on tr.drug_id=t.id",con)
ds=ds[ds.sentiment.isin(["positive","negative","no_effect"])].copy()   # drop mixed
ds["y"]=(ds.sentiment=="positive").astype(int)                          # helped vs didn't
ds["d"]=ds.drug.astype(str).str.lower()

GROUPS={"antihistamine/mast-cell":r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b|nasal spray","autonomic/cardiovascular":r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression|guanfacine|clonidine|pyridostigmine|mestinon","neuro-psychiatric":r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin|selective serotonin|antidepressant|xanax|fluvoxamine|mirtazapine|amitriptyline|nortriptyline","LDN/immunomodulator":r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine|colchicine","antiviral/anticoagulant":r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir|nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban|lumbrokinase|maraviroc","supplement/mitochondrial":r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|cannabidiol|\bcbd\b|alpha.?lipoic","peptide/experimental":r"bpc.?157|ss.?31|thymosin|peptide|rapamycin|sirolimus","metabolic":r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro","procedure/device":r"nicotine|hyperbaric|\bhbot\b|stellate ganglion|acupuncture|vagus|red light|\bvaccine\b"}
def grp(d):
    for g,p in GROUPS.items():
        if re.search(p,d): return g
    return None
ds["group"]=ds["d"].map(grp); ds=ds[ds.group.notna()].join(P,on="user_id").dropna(subset=PREDS)

report=[]; coef=[]
def W(s=""): report.append(s); print(s)
W("PER-DRUG-CATEGORY LOGIT (re-run sentiment) — P(helped) ~ conditions + severity")
W("  outcome: success=positive | failure=negative+no_effect | mixed dropped. predictors a-priori")
W(f"  total usable reports: {len(ds)} | overall helped-rate {ds.y.mean()*100:.0f}%\n")

for g in GROUPS:
    sub=ds[ds.group==g].drop_duplicates("user_id"); n=len(sub); y=sub.y.values
    ev=int(min(y.sum(),n-y.sum()))
    if n<60 or ev<15:
        W(f"  {g:28} n={n} fail-events={ev}  -> UNDERPOWERED (skipped)"); continue
    ok=[]
    for p in PREDS:
        if p=="nfields_z": ok.append(p); continue
        v=sub[p].values; s=v.sum()
        if s<max(6,0.05*n) or s>n-max(6,0.05*n): continue
        if y[v==1].sum() in (0,int((v==1).sum())) or y[v==0].sum() in (0,int((v==0).sum())): continue
        ok.append(p)
    conds=[p for p in ok if p in COND_SET]; sev=[p for p in ok if p not in COND_SET]
    budget=max(3, ev//8); sel=(conds+sev)[:budget] if len(conds)<=budget else sorted(conds,key=lambda p:-sub[p].sum())[:budget]
    for _ in range(len(sel)+1):
        try:
            m=sm.Logit(y,sm.add_constant(sub[sel].astype(float))).fit(disp=0,maxiter=200)
            if np.isfinite(m.bse).all() and (np.abs(m.params)<12).all(): break
        except Exception: pass
        try:
            worst=m.params.drop("const").abs().idxmax(); sel=[s for s in sel if s!=worst]
        except Exception: sel=[]; break
        if not sel: break
    if not sel:
        W(f"  {g:28} n={n} ev={ev}  -> no stable model"); continue
    ci=m.conf_int()
    W(f"  {g}  (n={n}, helped {int(y.sum())}/{n}={y.mean()*100:.0f}%, fail-events {ev})")
    rows=[(p,np.exp(m.params[p]),np.exp(ci.loc[p,0]),np.exp(ci.loc[p,1]),m.pvalues[p]) for p in sel]
    for p,orr,lo,hi,pv in sorted(rows,key=lambda x:x[1]):
        s="*" if pv<0.05 else " "
        W(f"    {s}OR={orr:5.2f} [{lo:4.2f},{hi:6.2f}] p={pv:.3f}  {('cond ' if p in COND_SET else 'sev  ')}{p}  {'predicts FAILURE' if orr<1 else 'predicts success'}")
        coef.append(dict(group=g,predictor=p,OR=orr,ci_lo=lo,ci_hi=hi,p=pv,coef=m.params[p],n=n))
    coef.append(dict(group=g,predictor="const",OR=np.nan,ci_lo=np.nan,ci_hi=np.nan,p=np.nan,coef=m.params["const"],n=n))
    W("")

W("  * p<0.05. outcome=helped vs (didn't help OR no effect). trajectory excluded (outcome-adjacent).")
(CLEAN/"drug_logit_rerun_report.txt").write_text("\n".join(report),encoding="utf-8")
pd.DataFrame(coef).to_csv(CLEAN/"drug_logit_coefficients_rerun.csv",index=False)
print("\nwrote: data/clean/drug_logit_rerun_report.txt + drug_logit_coefficients_rerun.csv")
