"""Stepped intake planning for the patient similarity layer."""

from __future__ import annotations

import re

from agentic_health_hackathon.shared_decision.models import (
    FeatureSource,
    FeatureValue,
    PatientFeatureVector,
    PatientIntake,
    QuestionStep,
    StepPlan,
)

ANCHOR_FEATURES = [
    "conditions=pots",
    "conditions=mcas",
    "conditions=dysautonomia",
    "conditions=me_cfs",
    "conditions=pem",
    "eds_any",
    "conditions=small_fiber_neuropathy",
    "conditions=fibromyalgia",
]


CONDITION_TO_FEATURE = {
    "pots": "conditions=pots",
    "mcas": "conditions=mcas",
    "dysautonomia": "conditions=dysautonomia",
    "me_cfs": "conditions=me_cfs",
    "pem": "conditions=pem",
    "eds": "eds_any",
    "eds_any": "eds_any",
    "eds_hypermobility_cci": "eds_any",
    "small_fiber_neuropathy": "conditions=small_fiber_neuropathy",
    "fibromyalgia": "conditions=fibromyalgia",
}


FEATURE_PATTERNS = {
    "conditions=pots": [
        r"\bpots\b",
        r"orthostatic",
        r"postural tachycardia",
        r"tachycardia",
    ],
    "conditions=mcas": [
        r"\bmcas\b",
        r"mast cell",
        r"histamine",
        r"flushing",
        r"hives",
    ],
    "conditions=dysautonomia": [
        r"dysautonomia",
        r"autonomic",
        r"orthostatic intolerance",
    ],
    "conditions=me_cfs": [
        r"\bme/cfs\b",
        r"\bmecfs\b",
        r"chronic fatigue syndrome",
        r"myalgic encephalomyelitis",
    ],
    "conditions=pem": [
        r"\bpem\b",
        r"post[- ]exertional",
        r"crash(?:es|ing)? after",
        r"exercise intolerance",
    ],
    "eds_any": [
        r"\beds\b",
        r"ehlers",
        r"hypermob",
        r"hypermobile",
        r"\bcci\b",
        r"craniocervical",
    ],
    "conditions=small_fiber_neuropathy": [
        r"small fiber",
        r"small fibre",
        r"\bsfn\b",
        r"burning",
        r"tingling",
        r"neuropath",
    ],
    "conditions=fibromyalgia": [
        r"fibromyalgia",
        r"\bfibro\b",
        r"widespread pain",
    ],
}


DEFAULT_QUESTION_STEPS = [
    QuestionStep(
        step_id="orthostatic",
        prompt=(
            "Do you have orthostatic symptoms, POTS, tachycardia, "
            "or symptoms that worsen upright?"
        ),
        response_type="boolean",
        maps_to_features=["conditions=pots", "conditions=dysautonomia"],
        rationale="Orthostatic features strongly affect neighbor placement and treatment context.",
    ),
    QuestionStep(
        step_id="mast_cell",
        prompt=(
            "Do you have histamine or mast-cell-like reactions such as flushing, "
            "hives, food reactions, or antihistamine response?"
        ),
        response_type="boolean",
        maps_to_features=["conditions=mcas"],
        rationale="Mast-cell features are one of the main treatment-response axes.",
    ),
    QuestionStep(
        step_id="pem",
        prompt=(
            "Do exertion, activity, or cognitive load trigger a delayed crash "
            "or post-exertional malaise?"
        ),
        response_type="boolean",
        maps_to_features=["conditions=pem", "conditions=me_cfs"],
        rationale="PEM and ME/CFS features help separate exertion-sensitive profiles.",
    ),
    QuestionStep(
        step_id="connective_tissue",
        prompt=(
            "Do you have hypermobility, EDS, CCI, frequent subluxations, "
            "or connective-tissue symptoms?"
        ),
        response_type="boolean",
        maps_to_features=["eds_any"],
        rationale="EDS is split across source fields, so the cross-field feature is preferred.",
    ),
    QuestionStep(
        step_id="neuropathy",
        prompt=(
            "Do you have neuropathy-like symptoms such as burning, tingling, "
            "numbness, or small fiber neuropathy?"
        ),
        response_type="boolean",
        maps_to_features=["conditions=small_fiber_neuropathy"],
        rationale=(
            "Neuropathy features affect both neighbor selection and treatment interpretation."
        ),
    ),
    QuestionStep(
        step_id="pain",
        prompt="Do you have fibromyalgia or widespread pain?",
        response_type="boolean",
        maps_to_features=["conditions=fibromyalgia"],
        rationale="Fibromyalgia was a notable treatment-heterogeneity marker in the logit work.",
    ),
    QuestionStep(
        step_id="functional_severity",
        prompt="Which best describes your current functional level?",
        response_type="single_select",
        maps_to_features=[
            "functional_status_tier=severe",
            "functional_status_tier=housebound",
            "functional_status_tier=bedbound",
            "functional_status_tier=mobility_limited",
        ],
        options=["mild", "working_limited", "mobility_limited", "housebound", "bedbound", "severe"],
        rationale="Severity should be a covariate and context feature, not a treatment outcome.",
    ),
    QuestionStep(
        step_id="already_tried",
        prompt="Which treatments have you already tried?",
        response_type="free_text",
        maps_to_features=[],
        rationale=(
            "Already-tried treatments should filter or annotate options, not define similarity."
        ),
    ),
]


def build_step_plan(intake: PatientIntake) -> StepPlan:
    """Map intake into features and return missing high-value questions."""
    vector = build_feature_vector(intake)
    missing = set(vector.missing_recommended_features)
    recommended = [
        step
        for step in DEFAULT_QUESTION_STEPS
        if not step.maps_to_features or all(feature in missing for feature in step.maps_to_features)
    ]
    return StepPlan(intake=intake, feature_vector=vector, recommended_steps=recommended)


def build_feature_vector(intake: PatientIntake) -> PatientFeatureVector:
    """Build a sparse patient feature vector from direct and text-derived intake."""
    features: dict[str, float] = {}
    mapped_values: list[FeatureValue] = []
    warnings: list[str] = []

    for slug in intake.condition_slugs:
        feature = CONDITION_TO_FEATURE.get(slug.strip().lower())
        if feature is None:
            warnings.append(f"Unsupported condition slug was ignored: {slug}")
            continue
        _set_feature(features, mapped_values, feature, source="direct", confidence=1.0)

    combined_text = " ".join(
        [*intake.symptoms, *intake.diagnoses, intake.free_text or ""]
    ).lower()
    for feature, patterns in FEATURE_PATTERNS.items():
        if feature in features:
            continue
        if any(re.search(pattern, combined_text) for pattern in patterns):
            _set_feature(features, mapped_values, feature, source="alias", confidence=0.75)

    if intake.functional_severity:
        for feature in _severity_features(intake.functional_severity):
            _set_feature(features, mapped_values, feature, source="severity", confidence=1.0)

    if intake.duration_months is not None:
        features["long_covid_duration_months"] = intake.duration_months
        mapped_values.append(
            FeatureValue(
                feature="long_covid_duration_months",
                value=intake.duration_months,
                source="duration",
                confidence=1.0,
            )
        )

    missing = [feature for feature in ANCHOR_FEATURES if feature not in features]
    if intake.already_tried_treatments:
        warnings.append(
            "Already-tried treatments are retained for filtering, not used for similarity."
        )

    return PatientFeatureVector(
        features=features,
        mapped_values=mapped_values,
        missing_recommended_features=missing,
        warnings=warnings,
    )


def _set_feature(
    features: dict[str, float],
    mapped_values: list[FeatureValue],
    feature: str,
    *,
    source: FeatureSource,
    confidence: float,
) -> None:
    features[feature] = 1.0
    mapped_values.append(
        FeatureValue(feature=feature, value=1.0, source=source, confidence=confidence)
    )


def _severity_features(value: str) -> list[str]:
    normalized = value.strip().lower().replace(" ", "_")
    aliases = {
        "bed_bound": "bedbound",
        "bedridden": "bedbound",
        "homebound": "housebound",
        "house_bound": "housebound",
        "wheelchair": "mobility_limited",
        "walker": "mobility_limited",
        "cane": "mobility_limited",
    }
    normalized = aliases.get(normalized, normalized)
    if normalized in {"severe", "very_severe"}:
        return ["functional_status_tier=severe", "func_severe"]
    if normalized in {"housebound", "bedbound", "mobility_limited", "working_limited"}:
        return [f"functional_status_tier={normalized}", f"func_{normalized}"]
    return []
