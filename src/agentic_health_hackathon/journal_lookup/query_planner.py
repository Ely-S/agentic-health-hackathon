"""Translate request inputs into PubMed-oriented search plans."""

from __future__ import annotations

from dataclasses import dataclass

from agentic_health_hackathon.journal_lookup.lexicon import ConceptLexicon, UnsupportedConceptError
from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    CanonicalConcept,
    PlannedQuery,
    ProblemProfile,
    SearchPlan,
)


@dataclass(frozen=True)
class RelevanceWeights:
    """Score weights used during article ranking."""

    mesh_match: float = 1.25
    title_match: float = 1.0
    abstract_match: float = 0.5
    review_bonus: float = 3.0
    trial_bonus: float = 2.5
    open_access_bonus: float = 0.5
    citation_bonus: float = 0.5
    recent_bonus: float = 0.5


class QueryPlanner:
    """Plan PubMed queries from canonical concepts and free text."""

    def __init__(self, lexicon: ConceptLexicon | None = None) -> None:
        self.lexicon = lexicon or ConceptLexicon()
        self.weights = RelevanceWeights()

    def create_plan(self, profile: ProblemProfile) -> SearchPlan:
        """Generate the concrete search plan for a request."""
        matched_concepts = self._resolve_requested_concepts(profile.canonical_concepts)
        notes: list[str] = []
        residual_free_text = None
        used_fallback = False

        if profile.free_text_query:
            detection = self.lexicon.detect(profile.free_text_query)
            for term in detection.ambiguous_terms:
                notes.append(f"Ambiguous alias skipped: {term}")
            detected_by_text = [
                concept
                for concept in detection.concepts
                if concept.slug not in {item.slug for item in matched_concepts}
            ]
            matched_concepts.extend(detected_by_text)
            matched_concepts = list(
                {concept.slug: concept for concept in matched_concepts}.values()
            )
            residual_free_text = detection.residual_text
            if not matched_concepts:
                used_fallback = True
            if detection.unmatched_terms:
                notes.append(
                    f"Preserved unmatched terms in search: {', '.join(detection.unmatched_terms)}"
                )

        broad_query = self._build_base_query(
            concepts=matched_concepts,
            residual_free_text=residual_free_text,
            start_year=profile.start_year,
            end_year=profile.end_year,
        )
        planned_queries = [
            PlannedQuery(stage="broad", query=broad_query, limit=profile.max_results),
            PlannedQuery(
                stage="review",
                query=f"{broad_query} AND (systematic[sb] OR meta-analysis[pt] OR review[pt])",
                limit=max(3, profile.max_results // 2),
            ),
            PlannedQuery(
                stage="trial",
                query=(
                    f"{broad_query} AND (clinical trial[pt] OR randomized[tiab] "
                    "OR prospective[tiab] OR intervention*[tiab])"
                ),
                limit=max(3, profile.max_results // 2),
            ),
        ]
        if matched_concepts and len(matched_concepts) > 2:
            notes.append(
                "Used OR-combined concept query because more than two concepts were provided."
            )
        return SearchPlan(
            profile=profile,
            matched_concepts=matched_concepts,
            residual_free_text=residual_free_text,
            exact_user_query=profile.free_text_query,
            exact_search_string=broad_query,
            planned_queries=planned_queries,
            used_fallback=used_fallback,
            notes=notes,
        )

    def score_article(self, article: ArticleHit, plan: SearchPlan) -> float:
        """Compute a lightweight relevance score for a fetched article."""
        haystack_title = article.citation.title.lower()
        haystack_abstract = (article.abstract or "").lower()
        mesh_terms = {term.lower() for term in article.mesh_terms}
        score = 0.0

        for concept in plan.matched_concepts:
            for mesh_term in concept.mesh_terms:
                if mesh_term.lower() in mesh_terms:
                    score += self.weights.mesh_match
            concept_terms = {
                concept.display_name.lower(),
                *[alias.lower() for alias in concept.aliases],
            }
            if any(term in haystack_title for term in concept_terms):
                score += self.weights.title_match
            if any(term in haystack_abstract for term in concept_terms):
                score += self.weights.abstract_match

        publication_types = {value.lower() for value in article.publication_types}
        if {"review", "systematic review", "meta-analysis"} & publication_types:
            score += self.weights.review_bonus
        if {
            "clinical trial",
            "randomized controlled trial",
            "observational study",
        } & publication_types:
            score += self.weights.trial_bonus
        if article.open_access:
            score += self.weights.open_access_bonus
        if (article.citation_count or 0) >= 10:
            score += self.weights.citation_bonus
        if (article.citation.publication_year or 0) >= 2020:
            score += self.weights.recent_bonus
        return score

    def _resolve_requested_concepts(self, slugs: list[str]) -> list[CanonicalConcept]:
        concepts: list[CanonicalConcept] = []
        for slug in slugs:
            try:
                concepts.append(self.lexicon.get(slug))
            except UnsupportedConceptError:
                concept = self.lexicon.resolve_alias(slug)
                if concept is None:
                    raise
                concepts.append(concept)
        deduped = {concept.slug: concept for concept in concepts}
        return list(deduped.values())

    def _build_base_query(
        self,
        *,
        concepts: list[CanonicalConcept],
        residual_free_text: str | None,
        start_year: int,
        end_year: int,
    ) -> str:
        concept_clauses = [self._concept_clause(concept) for concept in concepts]
        if concept_clauses:
            joiner = " AND " if len(concept_clauses) <= 2 else " OR "
            disease_clause = f"({joiner.join(concept_clauses)})"
        else:
            disease_clause = None

        text_clause = None
        if residual_free_text:
            text_clause = self._free_text_clause(residual_free_text)

        primary_clause = disease_clause
        if disease_clause and text_clause:
            primary_clause = f"({disease_clause} AND {text_clause})"
        elif text_clause:
            primary_clause = text_clause

        if primary_clause is None:
            msg = "Could not create a search query from the provided input."
            raise UnsupportedConceptError(msg)
        date_clause = (
            f'("{start_year}/01/01"[Date - Publication] : "{end_year}/12/31"[Date - Publication])'
        )
        return f"{primary_clause} AND humans[mh] AND {date_clause}"

    @staticmethod
    def _concept_clause(concept: CanonicalConcept) -> str:
        mesh_parts = [f'"{mesh_term}"[MeSH Terms]' for mesh_term in concept.mesh_terms]
        query_term_parts = [f'"{term}"[Title/Abstract]' for term in concept.query_terms]
        all_parts = mesh_parts + query_term_parts
        return f"({' OR '.join(all_parts)})"

    @staticmethod
    def _free_text_clause(text: str) -> str:
        sanitized = " ".join(piece.strip() for piece in text.split() if piece.strip())
        return f'"{sanitized}"[Title/Abstract]'
