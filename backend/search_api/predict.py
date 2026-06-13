"""
predict.py — wire our per-drug-category logit models into the API, with confidence intervals.

Loads the models fit in scripts/treatment_logit_rerun.py (on the corrected 5-class sentiment):
per drug class, the coefficient vector + covariance matrix. Given a patient's tracked variables,
returns each class's predicted probability of a *positive experience* and a 95% CI (error bar):
    logit = x·β,  var = xᵀ Σ x,  p = sigmoid(logit),  CI = sigmoid(logit ± 1.96·√var).
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .models import PredictRequest, PredictResponse, TreatmentPrediction

MODELS_PATH = Path(__file__).resolve().parent / "drug_logit_models.json"

# UI variable keys -> model predictor names
COND_MAP = {
    "pots": "pots", "mcas": "mcas", "dysautonomia": "dysautonomia",
    "me_cfs": "me_cfs", "cfs": "me_cfs", "pem": "pem",
    "sfn": "small_fiber_neuropathy", "small_fiber_neuropathy": "small_fiber_neuropathy",
    "fibromyalgia": "fibromyalgia", "fibro": "fibromyalgia",
    "eds": "eds_any", "eds_any": "eds_any",
}
# functional-status ladder (mild = reference, so it has no predictor)
SEV_MAP = {
    "moderate": "func_moderate", "mobility_limited": "func_mobility_limited",
    "housebound": "func_housebound", "bedbound": "func_bedbound",
}
LABEL = {
    "pots": "POTS", "mcas": "MCAS", "dysautonomia": "dysautonomia", "me_cfs": "ME/CFS",
    "pem": "PEM", "small_fiber_neuropathy": "small-fiber neuropathy",
    "fibromyalgia": "fibromyalgia", "eds_any": "EDS", "func_moderate": "moderate",
    "func_mobility_limited": "mobility-limited", "func_housebound": "housebound",
    "func_bedbound": "bedbound",
}

with open(MODELS_PATH, encoding="utf-8") as _f:
    MODELS = json.load(_f)   # group -> {predictors, beta, cov, n}


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def predict(req: PredictRequest) -> PredictResponse:
    active: set[str] = set()
    for c in req.conditions:
        key = str(c).strip().lower()
        if key in COND_MAP:
            active.add(COND_MAP[key])
    if req.severity and req.severity.strip().lower() in SEV_MAP:
        active.add(SEV_MAP[req.severity.strip().lower()])

    predictions: list[TreatmentPrediction] = []
    for group, m in MODELS.items():
        preds, beta, cov = m["predictors"], m["beta"], m["cov"]
        # x: 1 for const, 1 for an active predictor, 0 otherwise (nfields_z -> 0 = population mean)
        x = [1.0 if p == "const" else (1.0 if p in active else 0.0) for p in preds]
        logit = sum(xi * bi for xi, bi in zip(x, beta))
        var = sum(x[i] * cov[i][j] * x[j] for i in range(len(x)) for j in range(len(x)))
        se = math.sqrt(var) if var > 0 else 0.0
        p = _sigmoid(logit)
        lo = _sigmoid(logit - 1.96 * se)
        hi = _sigmoid(logit + 1.96 * se)
        base = _sigmoid(beta[0])
        drivers = sorted(
            ((preds[i], beta[i]) for i in range(len(preds)) if preds[i] in active),
            key=lambda d: -abs(d[1]),
        )
        driver_str = [f"{LABEL.get(pn, pn)} {'↑' if cf > 0 else '↓'}" for pn, cf in drivers[:3]]
        predictions.append(
            TreatmentPrediction(
                category=group,
                p_positive=round(p * 100),
                ci_lo=round(lo * 100),
                ci_hi=round(hi * 100),
                baseline=round(base * 100),
                delta=round((p - base) * 100),
                n=m["n"],
                drivers=driver_str,
                confidence="good" if m["n"] >= 150 else "limited",
            )
        )
    predictions.sort(key=lambda t: -t.p_positive)

    profile = [LABEL.get(COND_MAP[c.lower()], c) for c in req.conditions if c.lower() in COND_MAP]
    if req.severity and req.severity.strip().lower() in SEV_MAP:
        profile.append(LABEL[SEV_MAP[req.severity.strip().lower()]])
    elif req.severity and req.severity.strip().lower() == "mild":
        profile.append("mild")
    return PredictResponse(profile=profile, predictions=predictions)
