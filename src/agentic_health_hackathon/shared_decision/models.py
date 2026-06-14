"""Boundary models for shared-decision evidence orchestration."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from agentic_health_hackathon.journal_lookup.models import EvidenceSummary

QuestionResponseType = Literal["boolean", "single_select", "multi_select", "free_text"]
EvidencePosture = Literal["discuss", "caution", "insufficient_data"]
EvidenceConfidence = Literal["higher", "moderate", "low", "unavailable"]
SentimentLabel = Literal["positive", "negative", "no_effect", "mixed"]
FeatureSource = Literal["direct", "alias", "severity", "duration", "manual"]


def _dedupe_clean(values: list[str]) -> list[str]:
    cleaned = [value.strip() for value in values if value.strip()]
    return list(dict.fromkeys(cleaned))


class SafetyPolicy(BaseModel):
    """Safety and privacy rules attached to every shared-decision result."""

    model_config = ConfigDict(extra="forbid")

    disclaimer: str = (
        "This is lived-experience and literature navigation for clinician discussion, "
        "not medical advice, diagnosis, or a treatment recommendation."
    )
    privacy_note: str = (
        "Do not expose raw patient rows or full posting histories from the controlled dataset. "
        "Use short, reviewed snippets only when the display path is explicitly approved."
    )
    allowed_use: list[str] = Field(
        default_factory=lambda: [
            "Find similar patient-reported experiences.",
            "Summarize treatment signals with uncertainty.",
            "Prepare questions for shared decision-making with a clinician.",
        ]
    )
    hard_limits: list[str] = Field(
        default_factory=lambda: [
            "Do not claim clinical efficacy from Reddit reports.",
            "Do not use treatment or outcome fields to define patient similarity.",
            "Do not treat positive sentiment as equally reliable as negative sentiment.",
        ]
    )


class PatientIntake(BaseModel):
    """User-provided profile before feature mapping."""

    model_config = ConfigDict(extra="forbid")

    symptoms: list[str] = Field(default_factory=list)
    diagnoses: list[str] = Field(default_factory=list)
    condition_slugs: list[str] = Field(default_factory=list)
    functional_severity: str | None = None
    duration_months: float | None = Field(default=None, ge=0)
    already_tried_treatments: list[str] = Field(default_factory=list)
    treatment_goals: list[str] = Field(default_factory=list)
    free_text: str | None = None

    @field_validator(
        "symptoms",
        "diagnoses",
        "condition_slugs",
        "already_tried_treatments",
        "treatment_goals",
    )
    @classmethod
    def _clean_lists(cls, values: list[str]) -> list[str]:
        return _dedupe_clean(values)


class FeatureValue(BaseModel):
    """One mapped feature in the patient similarity space."""

    model_config = ConfigDict(extra="forbid")

    feature: str
    value: float = Field(ge=0)
    source: FeatureSource
    confidence: float = Field(default=1.0, ge=0, le=1)


class PatientFeatureVector(BaseModel):
    """Sparse patient vector compatible with the similarity layer."""

    model_config = ConfigDict(extra="forbid")

    features: dict[str, float] = Field(default_factory=dict)
    mapped_values: list[FeatureValue] = Field(default_factory=list)
    missing_recommended_features: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class QuestionStep(BaseModel):
    """A question that can improve placement in the patient similarity space."""

    model_config = ConfigDict(extra="forbid")

    step_id: str
    prompt: str
    response_type: QuestionResponseType
    maps_to_features: list[str]
    rationale: str
    options: list[str] = Field(default_factory=list)
    ask_when_missing: bool = True


class StepPlan(BaseModel):
    """Stepped intake plan plus current feature mapping."""

    model_config = ConfigDict(extra="forbid")

    intake: PatientIntake
    feature_vector: PatientFeatureVector
    recommended_steps: list[QuestionStep]


class NeighborPatient(BaseModel):
    """Pseudonymous neighbor summary from a controlled-data backend."""

    model_config = ConfigDict(extra="forbid")

    patient_key: str
    similarity: float = Field(ge=0, le=1)
    shared_features: list[str] = Field(default_factory=list)
    has_reviewed_snippets: bool = False
    snippet_refs: list[str] = Field(default_factory=list)


class SimilarityResult(BaseModel):
    """Nearest-neighbor retrieval result."""

    model_config = ConfigDict(extra="forbid")

    metric: str
    k_requested: int = Field(ge=1)
    neighbors: list[NeighborPatient] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class TreatmentSentimentCounts(BaseModel):
    """Aggregated patient-reported treatment sentiment counts."""

    model_config = ConfigDict(extra="forbid")

    positive: int = Field(default=0, ge=0)
    negative: int = Field(default=0, ge=0)
    no_effect: int = Field(default=0, ge=0)
    mixed: int = Field(default=0, ge=0)
    total: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def _set_total(self) -> TreatmentSentimentCounts:
        total = self.positive + self.negative + self.no_effect + self.mixed
        object.__setattr__(self, "total", total)
        return self


class NeighborTreatmentSignal(BaseModel):
    """Treatment signal aggregated from nearest neighbors."""

    model_config = ConfigDict(extra="forbid")

    treatment_slug: str
    display_name: str
    counts: TreatmentSentimentCounts
    weighted_score: float | None = None
    confidence: EvidenceConfidence = "unavailable"
    caveats: list[str] = Field(default_factory=list)


class LogitContribution(BaseModel):
    """One coefficient contributing to a logit score."""

    model_config = ConfigDict(extra="forbid")

    predictor: str
    coefficient: float
    feature_value: float


class LogitEstimate(BaseModel):
    """Per-drug-category logit score for a mapped patient."""

    model_config = ConfigDict(extra="forbid")

    treatment_group: str
    probability_helped: float | None = Field(default=None, ge=0, le=1)
    logit: float | None = None
    n_training_reports: int | None = Field(default=None, ge=0)
    contributions: list[LogitContribution] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)


class TreatmentOptionEvidence(BaseModel):
    """Joined evidence for one treatment option."""

    model_config = ConfigDict(extra="forbid")

    treatment_slug: str
    display_name: str
    neighbor_signal: NeighborTreatmentSignal | None = None
    logit_estimate: LogitEstimate | None = None
    literature_summary: EvidenceSummary | None = None
    literature_query_terms: list[str] = Field(default_factory=list)
    posture: EvidencePosture = "insufficient_data"
    caveats: list[str] = Field(default_factory=list)


class MissingCapability(BaseModel):
    """A data or service dependency that is intentionally not wired yet."""

    model_config = ConfigDict(extra="forbid")

    capability: str
    reason: str
    needed_input: str


class DecisionSupportResult(BaseModel):
    """Top-level shared-decision scaffold output."""

    model_config = ConfigDict(extra="forbid")

    safety: SafetyPolicy
    step_plan: StepPlan
    similarity: SimilarityResult | None = None
    treatment_options: list[TreatmentOptionEvidence] = Field(default_factory=list)
    missing_capabilities: list[MissingCapability] = Field(default_factory=list)
    next_actions: list[str] = Field(default_factory=list)
