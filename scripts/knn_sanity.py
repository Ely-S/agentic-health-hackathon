#!/usr/bin/env python3
"""
knn_sanity.py — validate the verbosity-controlled similarity space.

Claim to test: in the controlled (IDF + L2/cosine) space, a patient's nearest neighbors
share their *phenotype*; in raw presence space, neighbors are just *verbosity-matched*.

Reads data/clean/model_matrix_controlled.csv (controlled) + model_matrix.csv (raw presence,
same analysis-grade columns). Read-only. Prints results; writes nothing.
"""
from __future__ import annotations
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.neighbors import NearestNeighbors

ROOT = Path(__file__).resolve().parents[1]
CLEAN = ROOT / "data" / "clean"
KEY = "author_hash"
KAGG, KSHOW = 10, 5

ctrl = pd.read_csv(CLEAN / "model_matrix_controlled.csv")
full = pd.read_csv(CLEAN / "model_matrix.csv").set_index(KEY).loc[ctrl[KEY]].reset_index()
feat = [c for c in ctrl.columns if c not in (KEY, "n_fields_filled", "n_values", "eds_any")]
ids = ctrl[KEY].tolist()
nf = ctrl["n_fields_filled"].to_numpy(float)

Xc = ctrl[feat].to_numpy(float)            # controlled (IDF + L2 normalized)
Xr = full[feat].to_numpy(float)            # raw presence (0/1), same columns

# markers (phenotype) per patient
markers = {}
for canon in ["pots", "mcas", "me_cfs", "dysautonomia", "small_fiber_neuropathy", "fibromyalgia", "pem"]:
    col = f"conditions={canon}"
    markers[canon] = full[col].to_numpy(float) if col in full.columns else np.zeros(len(ids))
markers["eds_any"] = ctrl["eds_any"].to_numpy(float)
MN = list(markers)
M = np.array([markers[k] for k in MN]).T   # N x len(MN)

# restrict to patients with >=1 analysis feature (cosine undefined for all-zero rows)
mask = Xr.sum(1) > 0
keep = np.where(mask)[0]
Xc, Xr, M, nf2, ids2 = Xc[keep], Xr[keep], M[keep], nf[keep], [ids[i] for i in keep]
print(f"patients with >=1 analysis feature: {len(keep)} / {len(ids)}")

def knn(X, k):
    nn = NearestNeighbors(n_neighbors=k + 1, metric="cosine").fit(X)
    return nn.kneighbors(X, return_distance=False)[:, 1:]   # drop self

Kc, Kr = knn(Xc, KAGG), knn(Xr, KAGG)

# ---- aggregate metrics -------------------------------------------------------
def marker_agreement(K):
    """For each seed with >=1 marker: mean over neighbors of (fraction of the seed's markers
    the neighbor also has). >> base rate ⇒ neighbors share phenotype."""
    has = M.sum(1) > 0
    s = []
    for i in np.where(has)[0]:
        sm = M[i] > 0
        s.append((M[K[i]][:, sm] > 0).mean())
    return float(np.mean(s))

def verbosity_match(K):
    nbr = nf2[K].mean(1)
    absdiff = float(np.mean([np.abs(nf2[i] - nf2[K[i]]).mean() for i in range(len(nf2))]))
    r = float(np.corrcoef(nf2, nbr)[0, 1])
    return absdiff, r

base = float(np.mean([M[:, m].mean() for m in range(M.shape[1])]))   # rough chance level
ad_c, r_c = verbosity_match(Kc)
ad_r, r_r = verbosity_match(Kr)
print("\n=== AGGREGATE (k=10 neighbors, all marker-bearing seeds) ===")
print(f"  marker agreement (share of seed's markers a neighbor has):")
print(f"      controlled = {marker_agreement(Kc):.2f}   raw presence = {marker_agreement(Kr):.2f}"
      f"   (chance ~ {base:.2f})")
print(f"  verbosity match of neighbors  (want LOW for controlled):")
print(f"      mean |Δn_fields|:  controlled = {ad_c:.1f}   raw = {ad_r:.1f}")
print(f"      corr(seed n_fields, neighbors' n_fields):  controlled = {r_c:+.2f}   raw = {r_r:+.2f}")

# ---- concrete seed examples --------------------------------------------------
def desc(i):
    ms = [MN[j] for j in range(len(MN)) if M[i, j] > 0]
    return f"nf={int(nf2[i]):2d}  [{', '.join(ms) if ms else 'no markers'}]"

def find_seed(cond):
    cands = [i for i in range(len(ids2)) if cond(M[i])]
    if not cands:
        return None
    return sorted(cands, key=lambda i: abs(nf2[i] - np.median(nf2[cands])))[0]  # median-verbosity rep

seeds = {
    "POTS + MCAS": find_seed(lambda m: m[MN.index("pots")] and m[MN.index("mcas")]),
    "EDS (eds_any)": find_seed(lambda m: m[MN.index("eds_any")] and m[MN.index("pots")]),
    "ME/CFS + PEM": find_seed(lambda m: m[MN.index("me_cfs")] and m[MN.index("pem")]),
}
Kc5, Kr5 = knn(Xc, KSHOW), knn(Xr, KSHOW)
for name, i in seeds.items():
    if i is None:
        continue
    print(f"\n=== seed: {name}  ({desc(i)}) ===")
    print("  CONTROLLED neighbors (should share phenotype):")
    for j in Kc5[i]:
        print(f"      {desc(j)}")
    print("  RAW presence neighbors (tend to be verbosity-matched):")
    for j in Kr5[i]:
        print(f"      {desc(j)}")
