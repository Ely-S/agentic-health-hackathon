"""
predict.py — wire our per-drug-category logit models into the API.

Loads the coefficients fit in scripts/treatment_logit_rerun.py (on the corrected 5-class
sentiment) and, given a patient's tracked variables (conditions + functional severity), returns
each drug-mechanism class's predicted probability of a *positive experience* for someone with
that profile — logit = const + sum(coef * variable), p = sigmoid(logit).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

from .models import PredictRequest, PredictResponse, TreatmentPrediction

COEF_PATH = Path(__file__).resolve().parent / "drug_logit_coefficients.csv"

# UI variable keys -> model predictor names
COND_MAP = {
    "pots": "pots", "mcas": "mcas", "dysautonomia": "dysautonomia",
    "me_cfs": "me_cfs", "cfs": "me_cfs", "pem": "pem",
    "sfn": "small_fiber_neuropathy", "small_fiber_neuropathy": "small_fiber_neuropathy",
    "fibromyalgia": "fibromyalgia", "fibro": "fibromyalgia",
    "eds": "eds_any", "eds_any": "eds_any",
}
SEV_MAP = {
    "severe": "func_severe", "housebound": "func_housebound",
    "bedbound": "func_bedbound", "mobility_limited": "func_mobility_limited",
}
LABEL = {
    "pots": "POTS", "mcas": "MCAS", "dysautonomia": "dysautonomia", "me_cfs": "ME/CFS",
    "pem": "PEM", "small_fiber_neuropathy": "small-fiber neuropathy",
    "fibromyalgia": "fibromyalgia", "eds_any": "EDS", "func_severe": "severe status",
    "func_housebound": "housebound", "func_bedbound": "bedbound",
    "func_mobility_limited": "mobility-limited",
}


def _load() -> tuple[dict[str, dict[str, float]], dict[str, int]]:
    groups: dict[str, dict[str, float]] = {}
    ns: dict[str, int] = {}
    with open(COEF_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            groups.setdefault(row["group"], {})[row["predictor"]] = float(row["coef"])
            ns[row["group"]] = int(float(row["n"]))
    return groups, ns


GROUPS, NS = _load()


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def predict(req: PredictRequest) -> PredictResponse:
    active: set[str] = set()
    for c in req.conditions:
        key = str(c).strip().lower()
        if key in COND_MAP:
            active.add(COND_MAP[key])
    if req.severity and req.severity.strip().lower() in SEV_MAP:
        active.add(SEV_MAP[req.severity.strip().lower()])

    predictions: list[TreatmentPrediction] = []
    for group, coefs in GROUPS.items():
        const = coefs.get("const", 0.0)
        logit = const
        drivers: list[tuple[str, float]] = []
        for pred, coef in coefs.items():
            if pred in ("const", "nfields_z"):   # nfields_z is unknown for a new patient -> 0
                continue
            if pred in active:
                logit += coef
                drivers.append((pred, coef))
        p = _sigmoid(logit)
        base = _sigmoid(const)
        drivers.sort(key=lambda d: -abs(d[1]))
        driver_str = [f"{LABEL.get(pn, pn)} {'↑' if cf > 0 else '↓'}" for pn, cf in drivers[:3]]
        predictions.append(
            TreatmentPrediction(
                category=group,
                p_positive=round(p * 100),
                baseline=round(base * 100),
                delta=round((p - base) * 100),
                n=NS.get(group, 0),
                drivers=driver_str,
                confidence="good" if NS.get(group, 0) >= 150 else "limited",
            )
        )
    predictions.sort(key=lambda t: -t.p_positive)

    profile = [LABEL.get(COND_MAP[c.lower()], c) for c in req.conditions if c.lower() in COND_MAP]
    if req.severity and req.severity.strip().lower() in SEV_MAP:
        profile.append(LABEL[SEV_MAP[req.severity.strip().lower()]])
    return PredictResponse(profile=profile, predictions=predictions)
