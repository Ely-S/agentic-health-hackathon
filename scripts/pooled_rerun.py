#!/usr/bin/env python3
"""pooled_rerun.py — pooled partially-pooled heterogeneity model on the RE-RUN 5-class sentiment.
P(helped) ~ drug_group*condition + severity covars; helped=positive vs failed=(negative+no_effect);
mixed dropped. L2 partial pooling, patient-bootstrap CIs. Writes report to cleaned_v2/."""
from __future__ import annotations
import re, warnings
from pathlib import Path
import numpy as np, pandas as pd
from sklearn.linear_model import LogisticRegression
warnings.simplefilter("ignore")
ROOT=Path(__file__).resolve().parents[1]; CLEAN=ROOT/"data"/"clean"; KEY="author_hash"
B=150; SEED=0; rng=np.random.default_rng(SEED)
ctrl=pd.read_csv(CLEAN/"model_matrix_controlled.csv"); full=pd.read_csv(CLEAN/"model_matrix.csv").set_index(KEY)
CONDS=["pots","mcas","dysautonomia","me_cfs","pem","small_fiber_neuropathy","fibromyalgia","eds_any"]
pt=pd.DataFrame({KEY:ctrl[KEY]})
for c in CONDS[:-1]:
    col=f"conditions={c}"; pt[c]=full[col].reindex(ctrl[KEY]).fillna(0).to_numpy() if col in full.columns else 0
pt["eds_any"]=ctrl["eds_any"].to_numpy()
pt["nfields_z"]=((ctrl["n_fields_filled"]-ctrl["n_fields_filled"].mean())/ctrl["n_fields_filled"].std()).to_numpy()
COVARS=["nfields_z"]
for col in full.columns:
    if col.startswith("functional_status_tier="): pt[col]=full[col].reindex(ctrl[KEY]).fillna(0).to_numpy(); COVARS.append(col)
pt=pt.set_index(KEY)
GROUPS={"antihistamine/mast-cell":r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b","autonomic/cardiovascular":r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression|guanfacine|clonidine|pyridostigmine|mestinon","neuro-psychiatric":r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin|antidepressant|fluvoxamine|mirtazapine|amitriptyline","LDN/immunomodulator":r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine|colchicine","antiviral/anticoagulant":r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|nattokinase|serrapeptase|aspirin|anticoag|apixaban|maraviroc","supplement/mitochondrial":r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|alpha.?lipoic","metabolic":r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro"}
GLIST=list(GROUPS)
ds=pd.read_csv(CLEAN/"cleaned_v2"/"drug_sentiment.csv")
ds=ds[ds.sentiment.isin(["positive","negative","no_effect"])].copy(); ds["d"]=ds.drug.astype(str).str.lower()
ds["y"]=(ds.sentiment=="positive").astype(int)
def grp(d):
    for g,p in GROUPS.items():
        if re.search(p,d): return g
    return None
ds["group"]=ds["d"].map(grp); ds=ds[ds.group.notna()].join(pt,on="user_id").dropna(subset=CONDS+COVARS)
DCOLS=([f"drug={g}" for g in GLIST[1:]]+[f"cond={c}" for c in CONDS]+[f"drug={g}:cond={c}" for g in GLIST[1:] for c in CONDS]+COVARS)
gi={c:k for k,c in enumerate(DCOLS)}
def design(df):
    X=np.zeros((len(df),len(DCOLS))); gr=df["group"].to_numpy(); cd={c:df[c].to_numpy() for c in CONDS}
    for g in GLIST[1:]:
        isg=(gr==g).astype(float); X[:,gi[f"drug={g}"]]=isg
        for c in CONDS: X[:,gi[f"drug={g}:cond={c}"]]=isg*cd[c]
    for c in CONDS: X[:,gi[f"cond={c}"]]=cd[c]
    for cv in COVARS: X[:,gi[cv]]=df[cv].to_numpy()
    return X
X=design(ds); y=ds.y.to_numpy(); pat=ds.user_id.to_numpy(); uniq=np.unique(pat); rbp={p:np.where(pat==p)[0] for p in uniq}
fit=lambda Xm,ym: LogisticRegression(penalty="l2",C=1.0,max_iter=3000).fit(Xm,ym)
boot={(g,c):[] for g in GLIST[1:] for c in CONDS}
for b in range(B):
    idx=np.concatenate([rbp[p] for p in rng.choice(uniq,len(uniq),replace=True)])
    try: m=fit(X[idx],y[idx])
    except Exception: continue
    cb=dict(zip(DCOLS,m.coef_[0]))
    for g in GLIST[1:]:
        for c in CONDS: boot[(g,c)].append(cb[f"drug={g}:cond={c}"])
R=[]
def W(s=""): R.append(s); print(s)
W("POOLED MODEL on RE-RUN sentiment — P(helped) ~ drug_group*condition + severity")
W(f"  {len(ds)} reports (helped vs neg+no_effect; mixed dropped) | helped-rate {y.mean()*100:.0f}%")
W(f"  ref group '{GLIST[0]}'; L2 partial pooling; {B} patient-bootstraps\n")
W("== significant drug_group x condition interactions (95% CI excludes 1) ==")
sig=[]
for g in GLIST[1:]:
    for c in CONDS:
        a=np.array(boot[(g,c)]);
        if not len(a): continue
        orr,lo,hi=np.exp(np.median(a)),np.exp(np.percentile(a,2.5)),np.exp(np.percentile(a,97.5))
        if lo>1 or hi<1: sig.append((abs(np.log(orr)),g,c,orr,lo,hi))
for _,g,c,orr,lo,hi in sorted(sig,reverse=True):
    W(f"   {'BETTER' if orr>1 else 'WORSE '}  OR={orr:4.2f} [{lo:4.2f},{hi:5.2f}]   {g:26} x {c}")
if not sig: W("   (none)")
W("\n  vs OLD-sentiment pooled: neuro-psych×EDS, metabolic×SFN/fibro, antiviral×MCAS, supp×ME/CFS.")
(CLEAN/"cleaned_v2"/"treatment_pooled_report.txt").write_text("\n".join(R),encoding="utf-8")
print("\nwrote: data/clean/cleaned_v2/treatment_pooled_report.txt")
