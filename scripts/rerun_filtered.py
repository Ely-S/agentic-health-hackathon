#!/usr/bin/env python3
"""
rerun_filtered.py — re-run the pooled interaction model + per-drug logits with positive/weak
reports DROPPED, and compare the key signals to the full-data fit. Tests how much (if any)
predictive signal is lost by removing the contaminated positive/weak stratum.
"""
from __future__ import annotations
import re, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
import statsmodels.api as sm
warnings.simplefilter("ignore")

ROOT = Path(__file__).resolve().parents[1]; CLEAN = ROOT/"data"/"clean"; KEY="author_hash"
B = 150; C_REG = 1.0; SEED = 0
rng = np.random.default_rng(SEED)

ctrl = pd.read_csv(CLEAN/"model_matrix_controlled.csv")
man = pd.read_csv(CLEAN/"column_manifest.csv")
full = pd.read_csv(CLEAN/"model_matrix.csv").set_index(KEY)
CONDS = ["pots","mcas","dysautonomia","me_cfs","pem","small_fiber_neuropathy","fibromyalgia","eds_any"]
pt = pd.DataFrame({KEY: ctrl[KEY]})
for c in CONDS[:-1]:
    col=f"conditions={c}"; pt[c]= full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
pt["eds_any"]=ctrl["eds_any"].to_numpy()
pt["nfields_z"]=((ctrl["n_fields_filled"]-ctrl["n_fields_filled"].mean())/ctrl["n_fields_filled"].std()).to_numpy()
COVARS=["nfields_z"]
for col in full.columns:
    if col.startswith("functional_status_tier=") or col.startswith("symptom_trajectory="):
        pt[col]=full[col].reindex(ctrl[KEY]).fillna(0).to_numpy(); COVARS.append(col)
pt=pt.set_index(KEY)

GROUPS={"antihistamine/mast-cell":r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b","autonomic/cardiovascular":r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression","neuro-psychiatric":r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin","LDN/immunomodulator":r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine|colchicine","antiviral/anticoagulant":r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|famciclovir|nattokinase|serrapeptase|aspirin|anticoag|apixaban|rivaroxaban","supplement/mitochondrial":r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose","metabolic":r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro"}
GLIST=list(GROUPS)
ds0=pd.read_csv(CLEAN.parent/"csv_export"/"drug_sentiment.csv")
ds0=ds0[ds0.sentiment.isin(["positive","negative"])].copy(); ds0["d"]=ds0.drug.astype(str).str.lower()
def grp(d):
    for g,p in GROUPS.items():
        if re.search(p,d): return g
    return None
ds0["group"]=ds0["d"].map(grp); ds0=ds0[ds0.group.notna()].join(pt,on="user_id").dropna(subset=CONDS+COVARS)
ds0["y"]=(ds0.sentiment=="positive").astype(int)

DCOLS=([f"drug={g}" for g in GLIST[1:]]+[f"cond={c}" for c in CONDS]
       +[f"drug={g}:cond={c}" for g in GLIST[1:] for c in CONDS]+COVARS)
gi={c:k for k,c in enumerate(DCOLS)}
def design(df):
    X=np.zeros((len(df),len(DCOLS))); grp_=df["group"].to_numpy(); cond={c:df[c].to_numpy() for c in CONDS}
    for g in GLIST[1:]:
        isg=(grp_==g).astype(float); X[:,gi[f"drug={g}"]]=isg
        for c in CONDS: X[:,gi[f"drug={g}:cond={c}"]]=isg*cond[c]
    for c in CONDS: X[:,gi[f"cond={c}"]]=cond[c]
    for cv in COVARS: X[:,gi[cv]]=df[cv].to_numpy()
    return X
def fit(Xm,ym): return LogisticRegression(penalty="l2",C=C_REG,max_iter=3000).fit(Xm,ym)
KEYS=[("neuro-psychiatric","eds_any"),("metabolic","small_fiber_neuropathy"),
      ("metabolic","fibromyalgia"),("antiviral/anticoagulant","mcas"),("supplement/mitochondrial","me_cfs")]
def pooled(df):
    X=design(df); y=df.y.to_numpy(); pat=df.user_id.to_numpy(); uniq=np.unique(pat)
    rbp={p:np.where(pat==p)[0] for p in uniq}; boot={k:[] for k in KEYS}
    for b in range(B):
        idx=np.concatenate([rbp[p] for p in rng.choice(uniq,len(uniq),replace=True)])
        try: m=fit(X[idx],y[idx])
        except Exception: continue
        cb=dict(zip(DCOLS,m.coef_[0]))
        for g,c in KEYS: boot[(g,c)].append(cb[f"drug={g}:cond={c}"])
    out={}
    for k in KEYS:
        a=np.array(boot[k]); out[k]=(np.exp(np.median(a)),np.exp(np.percentile(a,2.5)),np.exp(np.percentile(a,97.5)))
    return out

ds_full=ds0; ds_filt=ds0[~((ds0.sentiment=="positive")&(ds0.signal_strength=="weak"))]
print(f"pooled model: full n={len(ds_full)} | drop pos/weak n={len(ds_filt)}\n")
rf=pooled(ds_full); rd=pooled(ds_filt)
print(f"{'interaction':42}{'FULL OR [CI]':26}{'DROP pos/weak OR [CI]':26}")
print("-"*94)
for k in KEYS:
    of,lf,hf=rf[k]; od,ld,hd=rd[k]
    sf="*" if (lf>1 or hf<1) else " "; sd="*" if (ld>1 or hd<1) else " "
    print(f"  {k[0]+' x '+k[1]:40}{sf}{of:.2f} [{lf:.2f},{hf:.2f}]{'':6}{sd}{od:.2f} [{ld:.2f},{hd:.2f}]")
print("\n  * = 95% bootstrap CI excludes 1. (Do the 5 signals survive dropping positive/weak?)\n")

# ---- per-drug logits on FILTERED data (significant predictors) ----
WG={**GROUPS,"antihistamine/mast-cell":GROUPS["antihistamine/mast-cell"]+r"|nasal spray",
    "autonomic/cardiovascular":GROUPS["autonomic/cardiovascular"]+r"|guanfacine|clonidine|pyridostigmine|mestinon",
    "neuro-psychiatric":GROUPS["neuro-psychiatric"]+r"|selective serotonin|antidepressant|xanax|fluvoxamine|mirtazapine|amitriptyline|nortriptyline",
    "antiviral/anticoagulant":GROUPS["antiviral/anticoagulant"]+r"|lumbrokinase|maraviroc",
    "supplement/mitochondrial":GROUPS["supplement/mitochondrial"]+r"|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|cannabidiol|\bcbd\b|alpha.?lipoic"}
PREDS=[c for c in CONDS]+[c for c in pt.columns if c.startswith("symptom_trajectory=") or c.startswith("functional_status_tier=")]+["nfields_z"]
dF=pd.read_csv(CLEAN.parent/"csv_export"/"drug_sentiment.csv"); dF=dF[dF.sentiment.isin(["positive","negative"])].copy()
dF=dF[~((dF.sentiment=="positive")&(dF.signal_strength=="weak"))]; dF["d"]=dF.drug.astype(str).str.lower()
def wgrp(d):
    for g,p in WG.items():
        if re.search(p,d): return g
    return None
dF["group"]=dF["d"].map(wgrp); dF=dF[dF.group.notna()].join(pt,on="user_id").dropna(subset=PREDS); dF["y"]=(dF.sentiment=="positive").astype(int)
print("== per-drug logits on positive/weak-DROPPED data: significant predictors (p<0.05) ==")
for g in WG:
    sub=dF[dF.group==g].drop_duplicates("user_id"); n=len(sub);
    if n<60: continue
    y=sub.y.values; ev=int(min(y.sum(),n-y.sum()))
    if ev<12: print(f"  {g:28} n={n} ev={ev} underpowered"); continue
    ok=[p for p in PREDS if (p=='nfields_z') or (max(6,0.08*n)<=sub[p].sum()<=n-max(6,0.08*n) and y[sub[p].values==1].sum() not in (0,int((sub[p].values==1).sum())) and y[sub[p].values==0].sum() not in (0,int((sub[p].values==0).sum())))]
    cond=[p for p in ok if p in set(CONDS)]; sel=(cond+[p for p in ok if p not in set(CONDS)])[:max(2,ev//8)]
    try:
        m=sm.Logit(y,sm.add_constant(sub[sel].astype(float))).fit(disp=0,maxiter=200); ci=m.conf_int()
    except Exception: continue
    sig=[(p,np.exp(m.params[p]),np.exp(ci.loc[p,0]),np.exp(ci.loc[p,1]),m.pvalues[p]) for p in sel if m.pvalues[p]<0.05]
    if sig:
        print(f"  {g}  (n={n}, ev={ev})")
        for p,orr,lo,hi,pv in sorted(sig,key=lambda x:x[1]):
            print(f"     OR={orr:5.2f} [{lo:.2f},{hi:5.2f}] p={pv:.3f}  {p}  {'FAILURE' if orr<1 else 'success'}")
