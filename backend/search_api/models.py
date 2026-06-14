from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


Weight = Literal["low", "medium", "high", "exclude"]


class WeightedTerm(BaseModel):
    term: str = Field(min_length=1, max_length=120)
    weight: Weight

    @field_validator("term")
    @classmethod
    def normalize_term(cls, value: str) -> str:
        normalized = " ".join(value.split()).strip()
        if not normalized:
            raise ValueError("term must not be blank")
        return normalized


class KeywordSearchRequest(BaseModel):
    terms: list[WeightedTerm] = Field(min_length=1, max_length=12)
    post_limit: int = Field(default=16, ge=1, le=50)
    treatment_limit: int = Field(default=8, ge=1, le=25)
    min_treatment_users: int = Field(default=5, ge=1, le=50)

    @field_validator("terms")
    @classmethod
    def require_included_term(cls, value: list[WeightedTerm]) -> list[WeightedTerm]:
        if not any(term.weight != "exclude" for term in value):
            raise ValueError("at least one non-exclude term is required")
        return value


class SearchHistoryStep(BaseModel):
    term: str
    weight: Weight
    points: int
    any_count: int
    all_count: int


class SearchCounts(BaseModel):
    matched_posts: int
    matched_users: int
    all_terms_posts: int


class RankedPost(BaseModel):
    post_id: str
    user_id: str
    title: str
    excerpt: str
    flair: str
    post_date: int
    score: int
    matched_count: int
    matched_terms: list[str]
    matched_term_details: list[WeightedTerm]


class TreatmentSummary(BaseModel):
    name: str
    support: str
    unique_users: int
    reports: int
    positive: int
    negative: int
    mixed: int
    no_effect: int
    pct_positive: int
    normalized_score: float
    side_effects: list[str]


class CohortSuggestion(BaseModel):
    term: str
    condition_type: Literal["illness", "symptom"]
    matched_users: int
    pct_users: int


class RankedUser(BaseModel):
    user_id: str
    matched_posts: int
    total_score: int
    avg_score: float
    latest_post_date: int
    treatment_reports: int
    diagnoses: int
    first_post_date: int
    total_posts: int
    diagnosis_terms: list[str]
    treatment_terms: list[str]


class KeywordSearchResponse(BaseModel):
    source: str
    query_terms: list[WeightedTerm]
    counts: SearchCounts
    cohort_history: list[SearchHistoryStep]
    posts: list[RankedPost]
    ranked_users: list[RankedUser]
    top_treatments: list[TreatmentSummary]
    top_cohort_suggestions: list[CohortSuggestion]
    top_practitioners: list[PractitionerMention]


class PostDetailResponse(BaseModel):
    post_id: str
    user_id: str
    title: str
    body_text: str
    flair: str
    post_date: int


class UserPostsRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=255)
    terms: list[WeightedTerm] = Field(min_length=1, max_length=12)
    post_limit: int = Field(default=12, ge=1, le=50)

    @field_validator("terms")
    @classmethod
    def require_included_term(cls, value: list[WeightedTerm]) -> list[WeightedTerm]:
        if not any(term.weight != "exclude" for term in value):
            raise ValueError("at least one non-exclude term is required")
        return value


class UserPostsResponse(BaseModel):
    user_id: str
    posts: list[RankedPost]


class PractitionerMention(BaseModel):
    name: str
    unique_users: int
    mention_count: int


class MetadataResponse(BaseModel):
    source: str
    post_count: int
    treatment_report_count: int
    treatment_user_count: int


# ---- treatment-outcome prediction (our per-category logit models in the UI) ----

class PredictRequest(BaseModel):
    """The patient's tracked variables: condition keys + an optional functional-severity level."""
    conditions: list[str] = Field(default_factory=list, max_length=20)
    severity: str | None = Field(default=None, max_length=40)


class TreatmentPrediction(BaseModel):
    category: str                 # drug-mechanism class (the model unit)
    p_positive: int               # predicted % chance of a positive experience for THIS profile
    ci_lo: int                    # 95% CI lower bound (error bar) on p_positive
    ci_hi: int                    # 95% CI upper bound (error bar) on p_positive
    baseline: int                 # predicted % for a patient with none of the modelled conditions
    delta: int                    # p_positive - baseline (how the profile shifts the odds)
    n: int                        # reports the model was fit on (support / confidence)
    drivers: list[str]            # which of the patient's variables pushed it up/down
    confidence: str               # "good" | "limited" (from n)
    sample_drugs: list[str] = []  # representative drugs in this class (for tooltips)
    evidence_count: int = 0       # reports from similar-cohort patients for this class


class PredictResponse(BaseModel):
    profile: list[str]
    predictions: list[TreatmentPrediction]
    disclaimer: str = (
        "Hypothesis-generating decision support from lived-experience reports — NOT medical "
        "advice. Predictions are from a logistic model on observational, self-reported data."
    )


class Quote(BaseModel):
    text: str
    drug: str
    sentiment: str
    post_id: str


class TreatmentEvidenceResponse(BaseModel):
    """Predictions + a real similar-patient cohort + quoteable evidence per class."""
    profile: list[str]
    matched_patients: int
    quoteable: int
    predictions: list[TreatmentPrediction]
    quotes: dict[str, list[Quote]] = {}        # category -> sample quotes from the cohort
    disclaimer: str = (
        "Decision support from lived-experience reports — NOT medical advice. Cohort = patients "
        "with overlapping conditions; predictions are from a logistic model on self-reported data."
    )


class ComorbidityPattern(BaseModel):
    condition: str                # canonical co-condition label
    cohort_count: int             # patients in the profile cohort who also report it
    cohort_pct: int               # % of the cohort
    baseline_pct: int             # % of the whole patient population
    lift: float                   # cohort_pct / baseline_pct (>1 = enriched in patients like you)


class ComorbidityResponse(BaseModel):
    """Diagnosis Evidence: conditions enriched among patients who share the profile."""
    profile: list[str]
    cohort_size: int
    population: int
    patterns: list[ComorbidityPattern] = []
    disclaimer: str = (
        "Co-occurrence patterns from self-reported data — NOT a diagnosis. Enrichment means a "
        "condition is more common among patients like you than in the population; raise it with "
        "a clinician, do not self-diagnose."
    )


class LitSearchRequest(BaseModel):
    """Free-text (and/or canonical-concept) literature search over PubMed et al."""
    query: str = Field(default="", max_length=200)
    concepts: list[str] = Field(default_factory=list, max_length=10)
    max_results: int = Field(default=10, ge=1, le=25)


class LitClaim(BaseModel):
    text: str
    citation_ids: list[str] = []


class LitSection(BaseModel):
    title: str
    claims: list[LitClaim] = []


class LitArticle(BaseModel):
    citation_id: str
    title: str
    url: str
    journal: str | None = None
    year: int | None = None
    pmid: str | None = None
    doi: str | None = None
    evidence_type: str | None = None
    signal: str | None = None        # positive | mixed_or_negative | neutral | insufficient
    citation_count: int | None = None
    open_access: bool = False
    abstract: str = ""


class LitSearchResponse(BaseModel):
    query: str
    disclaimer: str = ""
    llm_summary: str | None = None   # narrative summary of the hits (when an LLM key is set)
    summary_source: str = "deterministic"   # "llm" | "deterministic"
    sections: list[LitSection] = []
    articles: list[LitArticle] = []
    error: str | None = None         # set if the lookup failed (network, no results)


class ExplainRequest(BaseModel):
    category: str = Field(min_length=1, max_length=80)
    conditions: list[str] = Field(default_factory=list, max_length=20)
    severity: str | None = Field(default=None, max_length=40)
    quotes: list[str] = Field(default_factory=list, max_length=12)   # real cohort quotes to ground the explanation


class ExplainResponse(BaseModel):
    category: str
    text: str
    source: str   # "llm" or "fallback"
