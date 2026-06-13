"""
evidence.py — wraps the predictor with a real similar-patient cohort (from patientpunk.db) and a
real-time LLM "why it might help" explanation.

treatment_evidence(req): logit predictions + a cohort of patients who share the profile's
  conditions, the count with quoteable treatment reports, and a couple of real positive quotes
  per drug class.
explain(req): DeepSeek (via OpenRouter) writes a short, profile-specific, non-prescriptive blurb
  on what the class does and why it might/might not help; falls back to a templated line if no key.
"""
from __future__ import annotations

import json
import os
import re
import sqlite3
import urllib.request

from backend.shared_db import DB_PATH, connect_sqlite

from .models import ExplainRequest, ExplainResponse, PredictRequest, Quote, TreatmentEvidenceResponse
from .predict import SAMPLE_DRUGS, predict

# marker key -> condition_name LIKE patterns (for the cohort)
COND_LIKE = {
    "pots": ["pots", "postural orthostatic"], "mcas": ["mcas", "mast cell"],
    "dysautonomia": ["dysautonom", "autonomic"], "me_cfs": ["me/cfs", "mecfs", "chronic fatigue", "myalgic"],
    "pem": ["pem", "post-exertional", "post exertional"], "eds": ["eds", "ehlers", "hypermobil"],
    "small_fiber_neuropathy": ["small fiber", "small fibre", "sfn"], "fibromyalgia": ["fibro"],
}
# class -> drug regex (to bucket cohort reports into the predictor's classes)
CLASS_PATTERNS = {
    "antihistamine/mast-cell": r"antihistamine|cetirizine|loratadine|fexofenadine|famotidine|claritin|zyrtec|allegra|benadryl|diphenhydramine|hydroxyzine|cromolyn|ketotifen|quercetin|mast cell|\bh1\b|\bh2\b",
    "autonomic/cardiovascular": r"beta.?block|propranolol|metoprolol|bisoprolol|atenolol|nadolol|ivabradine|corlanor|midodrine|fludrocortisone|\bsalt\b|electrolyte|\bfluids?\b|compression|guanfacine|clonidine|pyridostigmine|mestinon",
    "neuro-psychiatric": r"ssri|snri|sertraline|fluoxetine|escitalopram|duloxetine|venlafaxine|prozac|zoloft|lexapro|cymbalta|abilify|aripiprazole|benzodiazepine|gabapentin|pregabalin|antidepressant|fluvoxamine|mirtazapine|amitriptyline",
    "LDN/immunomodulator": r"naltrexone|\bldn\b|prednisone|steroid|\bivig\b|rituximab|hydroxychloroquine",
    "antiviral/anticoagulant": r"paxlovid|nirmatrelvir|antiviral|valacyclovir|valtrex|nattokinase|serrapeptase|aspirin|anticoag|apixaban|maraviroc",
    "supplement/mitochondrial": r"magnesium|coq10|coenzyme|ubiquinol|\bb12\b|methylcobalamin|b complex|b vitamin|vitamin d|\bvit d\b|vitamin c|omega|fish oil|\bnad\b|nicotinamide|creatine|carnitine|d-ribose|\bnac\b|probiotic|\biron\b|melatonin|thiamine|methylene blue|glutathione|alpha.?lipoic",
    "peptide/experimental": r"bpc.?157|ss.?31|thymosin|peptide|rapamycin|sirolimus",
    "metabolic": r"metformin|tirzepatide|\bglp\b|semaglutide|ozempic|zepbound|mounjaro",
    "procedure/device": r"nicotine|hyperbaric|\bhbot\b|stellate ganglion|acupuncture|vagus|red light|\bvaccine\b",
}
_CLASS_RX = {c: re.compile(p) for c, p in CLASS_PATTERNS.items()}

# What each drug class does (mechanism), for the non-LLM explanation fallback.
CLASS_MECHANISM = {
    "antihistamine/mast-cell": "block histamine (H1/H2) and stabilize mast cells to dampen the mediator release behind flushing, hives, GI upset, and flares",
    "autonomic/cardiovascular": "act on heart rate, blood volume, and vascular tone to blunt orthostatic intolerance and tachycardia",
    "neuro-psychiatric": "modulate neurotransmitters and nerve signaling to target pain, sleep, mood, and autonomic regulation",
    "LDN/immunomodulator": "aim to recalibrate immune and glial signaling (e.g. low-dose naltrexone), with reported effects on fatigue, pain, and inflammation",
    "antiviral/anticoagulant": "target persistent viral activity or the microclotting and endothelial dysfunction implicated in some Long COVID",
    "supplement/mitochondrial": "support cellular energy metabolism and correct common deficiencies that can worsen fatigue",
    "peptide/experimental": "are investigational agents proposed to aid tissue repair and immune modulation, with mostly anecdotal evidence so far",
    "metabolic": "act on glucose and metabolic pathways (e.g. metformin, GLP-1s), with emerging interest in fatigue and inflammation",
    "procedure/device": "are non-drug interventions (e.g. stellate-ganglion block, hyperbaric oxygen, vagus-nerve stimulation) aimed at autonomic or hypoxic mechanisms",
}
# Why a class is (or isn't) mechanistically relevant to a SPECIFIC condition the patient selected.
# Keyed by class -> UI condition key -> reason clause (reads after "this class ...").
CLASS_FIT = {
    "antihistamine/mast-cell": {
        "mcas": "directly targets the mast-cell activation that defines your MCAS",
        "pots": "can ease POTS because histamine-driven vasodilation worsens orthostatic symptoms",
        "dysautonomia": "may help because mast-cell mediators can aggravate autonomic instability",
    },
    "autonomic/cardiovascular": {
        "pots": "is the core of POTS management — controlling heart rate and supporting blood volume",
        "dysautonomia": "directly addresses your autonomic dysregulation",
        "mcas": "covers the cardiovascular symptoms that overlap MCAS",
    },
    "neuro-psychiatric": {
        "fibromyalgia": "includes first-line fibromyalgia agents (e.g. duloxetine, low-dose amitriptyline) for pain and sleep",
        "small_fiber_neuropathy": "includes gabapentinoids and SNRIs used for neuropathic pain",
        "me_cfs": "can target the pain, unrefreshing sleep, and dysregulation seen in ME/CFS",
    },
    "LDN/immunomodulator": {
        "me_cfs": "centers on low-dose naltrexone, one of the most-reported options for ME/CFS fatigue and pain",
        "fibromyalgia": "has a small evidence base for fibromyalgia pain",
        "pem": "is reported by some to reduce post-exertional symptom burden",
    },
    "antiviral/anticoagulant": {
        "pem": "targets the viral-persistence and microclot hypotheses linked to crashes",
        "me_cfs": "aims at the post-viral mechanisms some associate with ME/CFS",
    },
    "supplement/mitochondrial": {
        "me_cfs": "addresses the energy-metabolism deficits central to ME/CFS fatigue",
        "pem": "aims at the cellular energy failure implicated in post-exertional crashes",
        "fibromyalgia": "covers supplements (e.g. magnesium) commonly tried for fibromyalgia symptoms",
    },
    "peptide/experimental": {
        "mcas": "is tried experimentally for immune modulation in MCAS",
        "me_cfs": "is tried experimentally for fatigue and tissue repair in ME/CFS",
    },
    "metabolic": {
        "me_cfs": "is being explored for the fatigue and inflammation seen in ME/CFS",
        "pem": "is of interest for the metabolic dysfunction behind crashes",
    },
    "procedure/device": {
        "pots": "includes stellate-ganglion block and vagus-nerve approaches that target autonomic dysfunction in POTS",
        "dysautonomia": "aims directly at autonomic regulation",
        "me_cfs": "includes HBOT and vagal approaches tried for ME/CFS fatigue",
    },
}


# What each class is *usually* aimed at — used to keep the no-direct-fit message class-specific.
CLASS_TYPICAL_FOR = {
    "antihistamine/mast-cell": "MCAS and histamine-driven symptoms",
    "autonomic/cardiovascular": "POTS and dysautonomia",
    "neuro-psychiatric": "fibromyalgia, neuropathic pain, and sleep/mood",
    "LDN/immunomodulator": "ME/CFS and fibromyalgia fatigue and pain",
    "antiviral/anticoagulant": "post-viral crashes (PEM) and microclotting",
    "supplement/mitochondrial": "fatigue and energy support",
    "peptide/experimental": "experimental immune modulation and tissue repair",
    "metabolic": "fatigue and metabolic dysfunction",
    "procedure/device": "autonomic dysfunction in POTS/dysautonomia",
}


def _join_clauses(items: list[str]) -> str:
    if len(items) <= 1:
        return items[0] if items else ""
    if len(items) == 2:
        return f"{items[0]}, and {items[1]}"
    return ", ".join(items[:-1]) + f", and {items[-1]}"


def _cohort_users(con: sqlite3.Connection, conditions: list[str]) -> set[str]:
    likes = [f"%{p}%" for c in conditions for p in COND_LIKE.get(str(c).lower(), [])]
    if not likes:
        return set()
    where = " OR ".join(["lower(condition_name) LIKE ?"] * len(likes))
    return {r[0] for r in con.execute(f"SELECT DISTINCT user_id FROM conditions WHERE {where}", likes)}


def _snippet(text: str, drug: str, r: int = 120) -> str:
    t = text or ""
    i = t.lower().find((drug or "").lower())
    seg = t[: 2 * r] if i < 0 else t[max(0, i - r) : i + r]
    return " ".join(seg.split())[:260]


def treatment_evidence(req: PredictRequest) -> TreatmentEvidenceResponse:
    pr = predict(req)
    matched, quoteable, ev_count, quotes = 0, 0, {}, {}
    with connect_sqlite(DB_PATH, row_factory=sqlite3.Row) as con:
        cohort = _cohort_users(con, req.conditions)
        matched = len(cohort)
        if cohort:
            ph = ",".join("?" * len(cohort))
            rows = con.execute(
                f"""SELECT tr.post_id, tr.user_id, t.canonical_name AS drug, tr.sentiment,
                       p.title, p.body_text
                    FROM treatment_reports tr
                    JOIN treatment t ON t.id = tr.drug_id
                    JOIN posts p ON p.post_id = tr.post_id
                    WHERE tr.user_id IN ({ph}) AND tr.sentiment IN ('positive', 'negative')
                    ORDER BY tr.sentiment DESC""",
                list(cohort),
            ).fetchall()
            quoteable = len({r["user_id"] for r in rows})
            for row in rows:
                drug = (row["drug"] or "").lower()
                for cls, rx in _CLASS_RX.items():
                    if rx.search(drug):
                        ev_count[cls] = ev_count.get(cls, 0) + 1
                        if row["sentiment"] == "positive" and len(quotes.get(cls, [])) < 2:
                            snip = _snippet(row["body_text"] or row["title"] or "", row["drug"])
                            if len(snip) > 40:
                                quotes.setdefault(cls, []).append(
                                    Quote(text=snip, drug=row["drug"], sentiment=row["sentiment"], post_id=row["post_id"])
                                )
                        break
    for p in pr.predictions:
        p.evidence_count = ev_count.get(p.category, 0)
    return TreatmentEvidenceResponse(
        profile=pr.profile, matched_patients=matched, quoteable=quoteable,
        predictions=pr.predictions, quotes=quotes,
    )


def _llm(prompt: str) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("LLM_API_KEY")
    if not key:
        return None
    model = os.environ.get("LLM_MODEL", "deepseek/deepseek-chat")
    body = json.dumps({
        "model": model, "max_tokens": 230, "temperature": 0.3,
        "messages": [{"role": "user", "content": prompt}],
    }).encode("utf-8")
    rq = urllib.request.Request(
        "https://openrouter.ai/api/v1/chat/completions", data=body,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(rq, timeout=25) as resp:
            return json.loads(resp.read())["choices"][0]["message"]["content"].strip()
    except Exception:
        return None


def explain(req: ExplainRequest) -> ExplainResponse:
    pr = predict(PredictRequest(conditions=req.conditions, severity=req.severity))
    pred = next((p for p in pr.predictions if p.category == req.category), None)
    profile = ", ".join(pr.profile) or "no specific conditions selected"
    samples = ", ".join(SAMPLE_DRUGS.get(req.category, [])[:5])
    pct = pred.p_positive if pred else None
    drivers = ", ".join(pred.drivers) if pred and pred.drivers else ""
    prompt = (
        "You are a careful clinical-evidence assistant for a Long COVID patient-experience tool. "
        "This is NOT medical advice. "
        f"Patient profile: {profile}. Treatment class: '{req.category}' (example drugs: {samples}). "
        f"A logistic model fit on patient-reported outcomes predicts about {pct}% chance of a positive "
        f"experience for patients like this" + (f", most influenced by {drivers}" if drivers else "") + ". "
        "In 2-3 short, plain-language sentences: (1) what this class of treatment does / its proposed "
        "mechanism in Long COVID, and (2) why it might or might not help THIS specific profile. "
        "Be honest and non-prescriptive; do not invent dosing or overstate certainty."
    )
    text = _llm(prompt)
    if text:
        return ExplainResponse(category=req.category, text=text, source="llm")

    # Slice-aware deterministic fallback (no LLM key): combine the class mechanism with why it
    # fits the SPECIFIC conditions selected, so the text differs per profile, not just per drug.
    keys = [str(c).strip().lower() for c in req.conditions]
    mech = CLASS_MECHANISM.get(req.category, "act through several proposed mechanisms")
    fitmap = CLASS_FIT.get(req.category, {})
    fits = [fitmap[k] for k in keys if fitmap.get(k)]
    drugword = f"These ({samples})" if samples else "Drugs in this class"
    if fits:
        why = "For your profile, this class " + _join_clauses(fits) + "."
    elif keys:
        typical = CLASS_TYPICAL_FOR.get(req.category, "other presentations")
        why = (f"This class is usually aimed at {typical} rather than the conditions you selected, so the "
               "number below reflects how similar patients actually fared rather than a targeted rationale.")
    else:
        why = "Select your conditions to see how this class lines up with your specific phenotype."
    fb = (f"{drugword} {mech}. {why} The model puts the chance of a positive experience around "
          f"{pct}%" + (f", most influenced by {drivers}" if drivers else "") + ". "
          "This is lived-experience signal, not clinical proof — discuss any change with a clinician.")
    return ExplainResponse(category=req.category, text=fb, source="fallback")
