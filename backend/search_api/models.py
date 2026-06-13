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
