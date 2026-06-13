"""Pydantic boundary models for journal lookup."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CanonicalConcept(BaseModel):
    """Normalized problem concept supported by the lookup service."""

    model_config = ConfigDict(extra="forbid")

    slug: str
    display_name: str
    source_fields: list[str]
    aliases: list[str] = Field(default_factory=list)
    mesh_terms: list[str] = Field(default_factory=list)
    query_terms: list[str] = Field(default_factory=list)
    notes: str | None = None


class ProblemProfile(BaseModel):
    """Input request for literature retrieval."""

    model_config = ConfigDict(extra="forbid")

    canonical_concepts: list[str] = Field(default_factory=list)
    free_text_query: str | None = None
    max_results: int = Field(default=12, ge=1, le=50)
    start_year: int = Field(default=2000, ge=1900, le=3000)
    end_year: int = Field(default=3000, ge=1900, le=3000)
    include_similar_articles: bool = True

    @model_validator(mode="after")
    def _validate_inputs(self) -> ProblemProfile:
        if not self.canonical_concepts and not (self.free_text_query or "").strip():
            msg = "Provide at least one canonical concept or a free-text query."
            raise ValueError(msg)
        if self.start_year > self.end_year:
            msg = "start_year must be less than or equal to end_year."
            raise ValueError(msg)
        deduped = list(dict.fromkeys(self.canonical_concepts))
        object.__setattr__(self, "canonical_concepts", deduped)
        return self


class PlannedQuery(BaseModel):
    """An executable PubMed search query."""

    model_config = ConfigDict(extra="forbid")

    stage: Literal["broad", "review", "trial", "similar"]
    query: str
    limit: int = Field(ge=1, le=100)


class SearchPlan(BaseModel):
    """Search execution plan derived from a problem profile."""

    model_config = ConfigDict(extra="forbid")

    profile: ProblemProfile
    matched_concepts: list[CanonicalConcept]
    residual_free_text: str | None = None
    exact_user_query: str | None = None
    exact_search_string: str
    planned_queries: list[PlannedQuery]
    used_fallback: bool = False
    notes: list[str] = Field(default_factory=list)


class CitationRecord(BaseModel):
    """Reference metadata for a literature hit."""

    model_config = ConfigDict(extra="forbid")

    citation_id: str
    title: str
    url: str
    journal: str | None = None
    publication_year: int | None = None
    pmid: str | None = None
    doi: str | None = None
    evidence_type: str | None = None


class ArticleHit(BaseModel):
    """Fetched literature hit with enrichment fields."""

    model_config = ConfigDict(extra="forbid")

    citation: CitationRecord
    abstract: str | None = None
    mesh_terms: list[str] = Field(default_factory=list)
    publication_types: list[str] = Field(default_factory=list)
    authors: list[str] = Field(default_factory=list)
    open_access: bool = False
    full_text_url: str | None = None
    source_databases: list[str] = Field(default_factory=list)
    relevance_score: float = 0.0
    citation_count: int | None = None
    signal: Literal["positive", "mixed_or_negative", "neutral", "insufficient"] = "insufficient"
    signal_rationale: str | None = None
    matched_interventions: list[str] = Field(default_factory=list)


class EvidenceClaim(BaseModel):
    """A human-readable claim backed by one or more citations."""

    model_config = ConfigDict(extra="forbid")

    section: Literal[
        "what_the_literature_says",
        "interventions_with_positive_signal",
        "mixed_or_negative_evidence",
        "evidence_quality_and_gaps",
    ]
    text: str
    citation_ids: list[str] = Field(min_length=1)


class EvidenceSummary(BaseModel):
    """Structured literature summary returned to CLI callers."""

    model_config = ConfigDict(extra="forbid")

    query_plan: SearchPlan
    disclaimer: str
    what_the_literature_says: list[EvidenceClaim] = Field(default_factory=list)
    interventions_with_positive_signal: list[EvidenceClaim] = Field(default_factory=list)
    mixed_or_negative_evidence: list[EvidenceClaim] = Field(default_factory=list)
    evidence_quality_and_gaps: list[EvidenceClaim] = Field(default_factory=list)
    cited_articles: list[ArticleHit] = Field(default_factory=list)
    patient_reported_evidence: None = None


class RenderedSummary(BaseModel):
    """Rendered presentation output for the CLI."""

    model_config = ConfigDict(extra="forbid")

    markdown: str
    summary: EvidenceSummary
