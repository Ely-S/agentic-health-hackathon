"""Concept lexicon and normalization helpers."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from importlib import resources

from agentic_health_hackathon.journal_lookup.models import CanonicalConcept

AMBIGUOUS_ALIASES: dict[str, str] = {
    "ms": "The alias 'ms' is ambiguous. Use an explicit condition name instead.",
}
SEPARATOR_PATTERN = re.compile(r"[,;/]|(?:\band\b)", re.IGNORECASE)
MULTISPACE_PATTERN = re.compile(r"\s+")


class UnsupportedConceptError(ValueError):
    """Raised when a requested canonical concept is not supported."""


@dataclass(frozen=True)
class DetectionResult:
    """Output from free-text concept detection."""

    concepts: list[CanonicalConcept]
    residual_text: str | None
    ambiguous_terms: list[str]
    unmatched_terms: list[str]


class ConceptLexicon:
    """Loads and resolves canonical literature concepts."""

    def __init__(self) -> None:
        concepts_path = resources.files(
            "agentic_health_hackathon.journal_lookup.resources"
        ).joinpath("concepts.json")
        raw_concepts = json.loads(concepts_path.read_text(encoding="utf-8"))
        concepts = [CanonicalConcept.model_validate(item) for item in raw_concepts]
        self._concepts = {concept.slug: concept for concept in concepts}
        self._alias_to_slug = self._build_alias_index(concepts)

    @staticmethod
    def _build_alias_index(concepts: list[CanonicalConcept]) -> dict[str, str]:
        alias_to_slug: dict[str, str] = {}
        for concept in concepts:
            alias_to_slug[concept.slug.lower()] = concept.slug
            for alias in concept.aliases:
                alias_to_slug[alias.lower()] = concept.slug
        return alias_to_slug

    def supported_slugs(self) -> list[str]:
        """Return sorted supported canonical concept slugs."""
        return sorted(self._concepts)

    def get(self, slug: str) -> CanonicalConcept:
        """Return a canonical concept by slug."""
        normalized_slug = slug.strip().lower()
        if normalized_slug in AMBIGUOUS_ALIASES:
            raise UnsupportedConceptError(AMBIGUOUS_ALIASES[normalized_slug])
        try:
            return self._concepts[normalized_slug]
        except KeyError as exc:
            supported = ", ".join(self.supported_slugs())
            msg = f"Unsupported concept '{slug}'. Supported concepts: {supported}"
            raise UnsupportedConceptError(msg) from exc

    def resolve_alias(self, alias: str) -> CanonicalConcept | None:
        """Resolve a single alias or slug."""
        normalized = alias.strip().lower()
        if normalized in AMBIGUOUS_ALIASES:
            raise UnsupportedConceptError(AMBIGUOUS_ALIASES[normalized])
        slug = self._alias_to_slug.get(normalized)
        if slug is None:
            return None
        return self._concepts[slug]

    def detect(self, text: str) -> DetectionResult:
        """Find supported concepts in a free-text query."""
        lower_text = text.lower()
        matched_slugs: list[str] = []
        residual = lower_text
        ambiguous_terms: list[str] = []

        for alias in sorted(AMBIGUOUS_ALIASES, key=len, reverse=True):
            pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
            if pattern.search(residual):
                ambiguous_terms.append(alias)

        alias_items = sorted(
            self._alias_to_slug.items(), key=lambda item: len(item[0]), reverse=True
        )
        for alias, slug in alias_items:
            pattern = re.compile(rf"(?<!\w){re.escape(alias)}(?!\w)")
            if pattern.search(residual):
                matched_slugs.append(slug)
                residual = pattern.sub(" ", residual)

        normalized_residual = MULTISPACE_PATTERN.sub(" ", residual).strip(" ,;/")
        unmatched_terms = [
            term.strip()
            for term in SEPARATOR_PATTERN.split(normalized_residual)
            if term.strip() and len(term.strip()) > 2
        ]
        deduped_slugs = list(dict.fromkeys(matched_slugs))
        concepts = [self._concepts[slug] for slug in deduped_slugs]
        residual_text = normalized_residual or None
        return DetectionResult(
            concepts=concepts,
            residual_text=residual_text,
            ambiguous_terms=ambiguous_terms,
            unmatched_terms=unmatched_terms,
        )
