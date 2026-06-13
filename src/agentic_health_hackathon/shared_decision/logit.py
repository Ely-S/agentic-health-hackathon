"""Scoring helpers for per-drug-category logit coefficient artifacts."""

from __future__ import annotations

import csv
import math
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from agentic_health_hackathon.shared_decision.models import (
    LogitContribution,
    LogitEstimate,
    PatientFeatureVector,
)


class LogitCoefficient(BaseModel):
    """One row from a generated drug logit coefficient CSV."""

    model_config = ConfigDict(extra="forbid")

    group: str
    predictor: str
    coefficient: float = Field(alias="coef")
    odds_ratio: float | None = Field(default=None, alias="OR")
    ci_lo: float | None = None
    ci_hi: float | None = None
    p: float | None = None
    n: int | None = Field(default=None, ge=0)


class LogitCoefficientStore:
    """In-memory score layer for generated per-drug-category logit coefficients."""

    def __init__(self, coefficients: list[LogitCoefficient]) -> None:
        self._by_group: dict[str, list[LogitCoefficient]] = {}
        for coefficient in coefficients:
            self._by_group.setdefault(coefficient.group, []).append(coefficient)

    @classmethod
    def from_csv(cls, path: Path) -> LogitCoefficientStore:
        """Load generated coefficient rows from a CSV file."""
        with path.open(encoding="utf-8", newline="") as file:
            rows = [
                LogitCoefficient.model_validate(_normalize_row(row))
                for row in csv.DictReader(file)
            ]
        return cls(rows)

    def available_groups(self) -> list[str]:
        """Return groups that can be scored."""
        return sorted(self._by_group)

    def score(self, *, treatment_group: str, vector: PatientFeatureVector) -> LogitEstimate:
        """Score a patient vector for one treatment group."""
        rows = self._by_group.get(treatment_group)
        if not rows:
            return LogitEstimate(
                treatment_group=treatment_group,
                caveats=[f"No logit coefficients are available for group: {treatment_group}"],
            )

        const = next((row for row in rows if row.predictor == "const"), None)
        logit = const.coefficient if const else 0.0
        caveats = [
            "Logit scores are hypothesis-generating and observational.",
            "Use as a second opinion alongside nearest-neighbor treatment reports.",
        ]
        if const is None:
            caveats.append("No intercept row was found, so scoring used an intercept of 0.")

        contributions: list[LogitContribution] = []
        for row in rows:
            if row.predictor == "const":
                continue
            feature_value = _feature_value(row.predictor, vector)
            if row.predictor == "nfields_z" and feature_value == 0:
                caveats.append("nfields_z was unavailable for the new patient and was set to 0.")
            if feature_value == 0:
                continue
            contribution = row.coefficient * feature_value
            logit += contribution
            contributions.append(
                LogitContribution(
                    predictor=row.predictor,
                    coefficient=row.coefficient,
                    feature_value=feature_value,
                )
            )

        probability = _logistic(logit)
        n_training_reports = max((row.n or 0 for row in rows), default=0) or None
        return LogitEstimate(
            treatment_group=treatment_group,
            probability_helped=probability,
            logit=logit,
            n_training_reports=n_training_reports,
            contributions=contributions,
            caveats=list(dict.fromkeys(caveats)),
        )


def _normalize_row(row: dict[str, str]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in row.items():
        if key in {"coef", "OR", "ci_lo", "ci_hi", "p"}:
            normalized[key] = _float_or_none(value)
        elif key == "n":
            normalized[key] = _int_or_none(value)
        else:
            normalized[key] = value
    return normalized


def _feature_value(predictor: str, vector: PatientFeatureVector) -> float:
    features = vector.features
    if predictor in features:
        return features[predictor]
    if f"conditions={predictor}" in features:
        return features[f"conditions={predictor}"]
    if predictor.startswith("func_"):
        severity = predictor.removeprefix("func_")
        return features.get(f"functional_status_tier={severity}", 0.0)
    return 0.0


def _float_or_none(value: str | None) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _int_or_none(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    return int(float(value))


def _logistic(value: float) -> float:
    if value >= 0:
        z = math.exp(-value)
        return 1 / (1 + z)
    z = math.exp(value)
    return z / (1 + z)
