#!/usr/bin/env python3
"""
similarity.py — the "patients-like-me -> ranked treatments" core.

Given a patient profile (conditions/symptoms), find the most similar patients in the
verbosity-controlled cosine space, then rank treatments by what *those* patients reported
(re-run 5-class sentiment). Engine + a demo on example profiles.

  neighbors(profile, k)  -> k nearest patients (cosine in the IDF+L2 controlled space)
  recommend_drugs(...)   -> individual drugs ranked by SIMILARITY-WEIGHTED helped-rate among
                            neighbours (helped=positive; failed=negative+no_effect; mixed excluded),
                            vs the drug's population helped-rate (the personalization).
  recommend_groups(...)  -> the same rolled up to mechanism classes (always well-supported).
"""
from __future__ import annotations
import math, re
from pathlib import Path
import numpy as np, pandas as pd

ROOT = Path(__file__).resolve().parents[1]; CLEAN = ROOT/"data"/"clean"; KEY="author_hash"; N=4366
ctrl = pd.read_csv(CLEAN/"model_matrix_controlled.csv")
full = pd.read_csv(CLEAN/"model_matrix.csv").set_index(KEY)
META = {KEY, "n_fields_filled", "n_values", "eds_any"}
FEAT = [c for c in ctrl.columns if c not in META]
M = ctrl[FEAT].to_numpy(float); ids = ctrl[KEY].tolist()
w = np.array([math.log((1+N)/(1+(full[c].sum() if c in full.columns else 0)))+1 for c in FEAT])
fcol = {c: j for j, c in enumerate(FEAT)}

ds = pd.read_csv(CLEAN/"cleaned_v2"/"drug_sentiment.csv")
ds = ds[ds.sentiment.isin(["positive","negative","no_effect"])].copy()
BLOCK = {"mcas","supplement","supplements","supplementation","medication","medications",
         "new medications","adhd medication","drug","drugs","treatment","treatments","meds"}
ds = ds[~ds.drug.astype(str).str.lower().isin(BLOCK)]
ds["helped"] = (ds.sentiment == "positive").astype(int)
pop = ds.groupby("drug").helped.agg(["sum","size"]); pop = (pop["sum"]/pop["size"]).where(pop["size"]>=20)
GROUPS = {"antihistamine/mast-cell":r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b","autonomic/cardiovascular":r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression|guanfacine|clonidine|pyridostigmine|mestinon","neuro-psychiatric":r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin|antidepressant|fluvoxamine|mirtazapine|amitriptyline","LDN/immunomodulator":r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine","antiviral/anticoagulant":r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|nattokinase|serrapeptase|aspirin|anticoag|apixaban|maraviroc","supplement/mitochondrial":r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|alpha.?lipoic","metabolic":r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro"}
def grp(d):
    for g,p in GROUPS.items():
        if re.search(p,str(d).lower()): return g
    return None
ds["group"] = ds.drug.map(grp)

def make_query(conditions, symptoms=None):
    q = np.zeros(len(FEAT))
    for c in conditions:
        if f"conditions={c}" in fcol: q[fcol[f"conditions={c}"]] = 1.0
    for s in (symptoms or []):
        if s in fcol: q[fcol[s]] = 1.0
    q *= w; n = np.linalg.norm(q)
    return q/n if n else q

def neighbors(conditions, symptoms=None, k=300):
    sims = M @ make_query(conditions, symptoms)
    order = np.argsort(-sims)[:k]
    return order, sims[order]

def _agg(idx, sims, col, min_support):
    nbr = {ids[i]: s for i, s in zip(idx, sims)}
    sub = ds[ds.user_id.isin(nbr)].copy(); sub["sw"] = sub.user_id.map(nbr); sub["swh"] = sub.sw*sub.helped
    g = sub.groupby(col).agg(n=("helped","size"), helped=("helped","sum"),
                             sw=("sw","sum"), swh=("swh","sum"))
    g["wrate"] = g.swh/g.sw
    return g[g.n >= min_support]

def demo(name, conditions):
    idx, sims = neighbors(conditions, k=300)
    print(f"\n=== PATIENTS LIKE ME: {name}  ({'+'.join(conditions)}) ===")
    print(f"  {len(idx)} nearest neighbours, mean cosine {sims.mean():.2f}")
    grp_g = _agg(idx, sims, "group", 10).dropna().sort_values("wrate", ascending=False)
    print("  drug-CLASS ranking (similarity-weighted helped-rate | n reports):")
    for cls, r in grp_g.iterrows():
        print(f"     {r.wrate*100:3.0f}%  (n={int(r.n)})  {cls}")
    dg = _agg(idx, sims, "drug", 8).sort_values("wrate", ascending=False)
    dg["pop"] = dg.index.map(pop)
    print("  TOP individual treatments (helped-rate among similar | population | n):")
    for drug, r in dg.head(10).iterrows():
        oc = f"{r['pop']*100:.0f}%" if pd.notna(r['pop']) else " - "
        lift = "  <-- better than pop" if pd.notna(r['pop']) and r.wrate-r['pop']>0.12 else ""
        print(f"     {r.wrate*100:3.0f}%  (pop {oc}, n={int(r.n)})  {drug}{lift}")
    print("  CAUTION — lowest helped-rate among similar (n>=8):")
    for drug, r in dg.tail(4).sort_values("wrate").iterrows():
        print(f"     {r.wrate*100:3.0f}%  (n={int(r.n)})  {drug}")

print("patients:", len(ids), "| cosine features:", len(FEAT), "| usable drug reports:", len(ds))
demo("dysautonomia-spectrum", ["pots","mcas","dysautonomia"])
demo("fatigue-spectrum",      ["me_cfs","pem"])
demo("hypermobility-spectrum",["eds","pots","mcas"])
