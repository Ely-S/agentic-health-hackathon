"""
comorbidity.py — the Diagnosis Evidence mode, on real data.

Flips the question from "what helped people like me?" to "what diagnoses / phenotypes
recur in patients who look like me?". Given the same profile (conditions + severity), we take
the cohort of patients sharing those conditions and rank every OTHER condition by ENRICHMENT:

    lift = P(condition | cohort) / P(condition | whole population)

A lift > 1 means the condition is over-represented among patients like you — a co-occurrence
pattern worth raising with a clinician, NOT a diagnosis. Counts come straight from the
conditions table; messy free-text names are folded into curated canonical labels.
"""
from __future__ import annotations

import re
import sqlite3

from backend.shared_db import DB_PATH, connect_sqlite

from .models import ComorbidityPattern, ComorbidityResponse, PredictRequest
from .evidence import _cohort_users

# free-text condition_name -> clean canonical label (first match wins)
_CANON = [
    (re.compile(r"postural orthostatic|\bpots\b"), "POTS"),
    (re.compile(r"mast cell|\bmcas\b"), "MCAS"),
    (re.compile(r"dysautonom|autonomic"), "dysautonomia"),
    (re.compile(r"me/cfs|mecfs|myalgic|chronic fatigue"), "ME/CFS"),
    (re.compile(r"\bpem\b|post.?exertional"), "PEM"),
    (re.compile(r"ehlers|\beds\b|hypermobil"), "EDS / hypermobility"),
    (re.compile(r"small fib|\bsfn\b"), "small-fiber neuropathy"),
    (re.compile(r"fibro"), "fibromyalgia"),
    (re.compile(r"\bibs\b|irritable bowel"), "IBS"),
    (re.compile(r"gastroparesis"), "gastroparesis"),
    (re.compile(r"multiple sclerosis|\bms\b"), "multiple sclerosis"),
    (re.compile(r"lupus|\bsle\b"), "lupus"),
    (re.compile(r"lyme"), "Lyme disease"),
    (re.compile(r"rheumatoid"), "rheumatoid arthritis"),
    (re.compile(r"psoriatic"), "psoriatic arthritis"),
    (re.compile(r"ankylosing"), "ankylosing spondylitis"),
    (re.compile(r"endometriosis"), "endometriosis"),
    (re.compile(r"\bpcos\b"), "PCOS"),
    (re.compile(r"\bmito|mitochond"), "mitochondrial dysfunction"),
    (re.compile(r"hashimoto|hypothyroid|\bthyroid"), "thyroid disease"),
    (re.compile(r"sj.gren"), "Sjogren's"),
    (re.compile(r"\bcirs\b"), "CIRS"),
    (re.compile(r"\bfnd\b|functional neuro"), "FND"),
    (re.compile(r"craniocervical|\bcci\b"), "craniocervical instability"),
    (re.compile(r"\bme\b|chiari"), "Chiari / structural"),
    (re.compile(r"diabet"), "diabetes"),
    (re.compile(r"\bgerd\b|reflux"), "GERD"),
    (re.compile(r"migraine"), "migraine"),
    (re.compile(r"\bcrps\b"), "CRPS"),
    (re.compile(r"sibo"), "SIBO"),
]
# universal entry condition / non-informative trigger labels -> never a "pattern"
_EXCLUDE = re.compile(r"long covid|covid.?related|covid.?induced|covid.?triggered|post.?viral|covid.?19|^covid$")
# UI marker key -> the canonical label it would produce (so we don't surface the user's own inputs)
_SELF = {
    "pots": "POTS", "mcas": "MCAS", "dysautonomia": "dysautonomia", "me_cfs": "ME/CFS",
    "pem": "PEM", "eds": "EDS / hypermobility", "small_fiber_neuropathy": "small-fiber neuropathy",
    "fibromyalgia": "fibromyalgia",
}


def _canon(name: str) -> str | None:
    n = (name or "").strip().lower()
    if not n or _EXCLUDE.search(n):
        return None
    for rx, label in _CANON:
        if rx.search(n):
            return label
    # keep uncurated names only if they look like a real label (avoid junk fragments)
    return name.strip().title() if 3 <= len(n) <= 40 else None


def _user_conditions(con: sqlite3.Connection) -> dict[str, set[str]]:
    """canonical label -> set of user_ids reporting it."""
    out: dict[str, set[str]] = {}
    for uid, cn in con.execute("SELECT DISTINCT user_id, condition_name FROM conditions"):
        lab = _canon(cn)
        if lab:
            out.setdefault(lab, set()).add(uid)
    return out


def comorbidity(req: PredictRequest) -> ComorbidityResponse:
    self_labels = {_SELF[str(c).lower()] for c in req.conditions if str(c).lower() in _SELF}
    with connect_sqlite(DB_PATH, row_factory=None) as con:
        by_label = _user_conditions(con)
        population = {r[0] for r in con.execute("SELECT DISTINCT user_id FROM conditions")}
        cohort = _cohort_users(con, req.conditions)
    pop_n = len(population) or 1
    cohort_n = len(cohort)

    patterns: list[ComorbidityPattern] = []
    if cohort_n:
        for label, users in by_label.items():
            if label in self_labels:
                continue
            c_count = len(users & cohort)
            if c_count < 5:                      # too sparse to be a pattern
                continue
            cohort_pct = c_count / cohort_n
            baseline_pct = len(users) / pop_n
            lift = cohort_pct / baseline_pct if baseline_pct else 0.0
            patterns.append(
                ComorbidityPattern(
                    condition=label,
                    cohort_count=c_count,
                    cohort_pct=round(cohort_pct * 100),
                    baseline_pct=round(baseline_pct * 100),
                    lift=round(lift, 2),
                )
            )
    # rank by prevalence-in-cohort first, then enrichment (common AND distinctive float up)
    patterns.sort(key=lambda p: (-p.cohort_pct, -p.lift))
    return ComorbidityResponse(
        profile=sorted(self_labels), cohort_size=cohort_n, population=pop_n,
        patterns=patterns[:12],
    )
