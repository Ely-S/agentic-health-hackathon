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
    fb = (f"{req.category} (e.g. {samples}). For a profile of {profile}, the model estimates ~{pct}% "
          f"chance of a positive experience" + (f", driven by {drivers}." if drivers else ".") +
          " This reflects self-reported lived experience, not clinical efficacy — discuss with a clinician.")
    return ExplainResponse(category=req.category, text=fb, source="fallback")
