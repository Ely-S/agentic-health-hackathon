#!/usr/bin/env python3
"""
app.py — thin "patients-like-me" demo. Intake (free text) -> similar patients -> ranked
treatments + caution flags. Wraps scripts/similarity.py (the engine).

Usage:
    py -3 scripts/app.py "I have POTS and MCAS, severe fatigue and I crash after activity"
    py -3 scripts/app.py            # runs a default example profile

The free-text -> conditions step here is a keyword mapper; the agentic version would swap in an
LLM for intake/segmentation. Everything downstream (similarity + ranked treatments) is unchanged.
NOT medical advice — decision support from lived-experience reports.
"""
from __future__ import annotations
import sys, re
import pandas as pd
import similarity as S   # the engine: neighbors(), _agg(), pop, ids, full, GROUPS

# free text -> marker conditions (keyword mapper; LLM-replaceable)
PARSE = {
    "pots": r"pots|postural|orthostatic|tachycardi|racing heart|heart rate spikes",
    "mcas": r"mcas|mast cell|histamine|hives|flushing|food (reactions|sensitiv)",
    "dysautonomia": r"dysautonom|autonomic",
    "me_cfs": r"me/?cfs|chronic fatigue|\bcfs\b|myalgic",
    "pem": r"\bpem\b|post.?exertional|crash(es|ing)? after|payback|push.?crash",
    "eds": r"\bh?eds\b|ehlers|hypermobil|bendy|loose joints",
    "fibromyalgia": r"fibro",
    "small_fiber_neuropathy": r"small.?fib|\bsfn\b|burning (pain|feet)|neuropath",
}
MARK = ["pots","mcas","dysautonomia","me_cfs","pem","eds","small_fiber_neuropathy","fibromyalgia"]

def parse_profile(text: str):
    t = text.lower()
    return [c for c, p in PARSE.items() if re.search(p, t)]

def shared_conditions(idx, top=7):
    nbr = [S.ids[i] for i in idx]
    sub = S.full.loc[[n for n in nbr if n in S.full.index]]
    out = {}
    for m in MARK:
        col = f"conditions={'small_fiber_neuropathy' if m=='small_fiber_neuropathy' else m}"
        if col in sub.columns:
            out[m] = sub[col].mean()
    return sorted(out.items(), key=lambda x: -x[1])[:top]

def report(text: str, k: int = 300):
    conds = parse_profile(text)
    if not conds:
        return None
    idx, sims = S.neighbors(conds, k=k)
    classes = S._agg(idx, sims, "group", 10).dropna().sort_values("wrate", ascending=False)
    drugs = S._agg(idx, sims, "drug", 8); drugs["pop"] = drugs.index.map(S.pop)
    drugs = drugs.sort_values("wrate", ascending=False)
    return dict(conds=conds, k=len(idx), sim=float(sims.mean()),
                shared=shared_conditions(idx), classes=classes, drugs=drugs)

def render(text, r):
    L = []
    L.append("=" * 72)
    L.append("  PATIENTS LIKE ME  —  treatment decision-support (NOT medical advice)")
    L.append("=" * 72)
    L.append(f'  You said: "{text}"')
    L.append(f"  Parsed profile: {', '.join(r['conds'])}")
    L.append(f"\n  Found {r['k']} most-similar patients (avg similarity {r['sim']:.2f}). They commonly also report:")
    L.append("    " + "  ·  ".join(f"{m} {p*100:.0f}%" for m, p in r["shared"] if p > 0.05))
    L.append("\n  WHAT HELPED PEOPLE LIKE YOU — by treatment class (helped-rate | n reports):")
    for cls, row in r["classes"].iterrows():
        L.append(f"     {row.wrate*100:3.0f}%   (n={int(row.n)})   {cls}")
    L.append("\n  TOP SPECIFIC TREATMENTS (helped-rate among similar | typical | n):")
    for drug, row in r["drugs"].head(10).iterrows():
        pop = f"{row['pop']*100:.0f}%" if pd.notna(row["pop"]) else " — "
        star = "  ★ better than typical" if pd.notna(row["pop"]) and row.wrate - row["pop"] > 0.12 else ""
        L.append(f"     {row.wrate*100:3.0f}%   (typ {pop}, n={int(row.n)})   {drug}{star}")
    cautions = r["drugs"][r["drugs"].n >= 8].sort_values("wrate").head(4)
    if len(cautions):
        L.append("\n  ⚠  USE CAUTION — worked less often for people like you:")
        for drug, row in cautions.iterrows():
            L.append(f"     {row.wrate*100:3.0f}%   (n={int(row.n)})   {drug}")
    L.append("\n  Source: lived-experience reports from r/covidlonghaulers (controlled dataset).")
    L.append("  This is hypothesis-generating decision support, NOT medical advice. Talk to a clinician.")
    L.append("=" * 72)
    return "\n".join(L)

def main():
    text = sys.argv[1] if len(sys.argv) > 1 else \
        "I have POTS and MCAS with dysautonomia, severe fatigue and I crash hard after activity"
    r = report(text)
    if r is None:
        print("Could not recognise any conditions in the input. Try mentioning e.g. POTS, MCAS, "
              "ME/CFS, PEM, EDS, dysautonomia, fibromyalgia, or small-fiber neuropathy.")
        return
    print(render(text, r))

if __name__ == "__main__":
    main()
