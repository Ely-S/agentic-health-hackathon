"""UI-friendly helpers for journal lookup outputs."""

from __future__ import annotations

from dataclasses import dataclass

from agentic_health_hackathon.journal_lookup.lexicon import ConceptLexicon
from agentic_health_hackathon.journal_lookup.models import EvidenceClaim, EvidenceSummary


@dataclass(frozen=True)
class SummarySection:
    """Display-ready summary section."""

    title: str
    claims: list[EvidenceClaim]
    empty_message: str


def supported_problem_options() -> list[tuple[str, str]]:
    """Return canonical problem options for UI selection."""
    lexicon = ConceptLexicon()
    concepts = [lexicon.get(slug) for slug in lexicon.supported_slugs()]
    return [(concept.slug, concept.display_name) for concept in concepts]


def build_summary_sections(summary: EvidenceSummary) -> list[SummarySection]:
    """Return summary sections ordered for the UI."""
    return [
        SummarySection(
            title="What the literature says",
            claims=summary.what_the_literature_says,
            empty_message="No overview claims were generated.",
        ),
        SummarySection(
            title="Interventions with positive signal",
            claims=summary.interventions_with_positive_signal,
            empty_message="No positive intervention signal was found.",
        ),
        SummarySection(
            title="Mixed or negative evidence",
            claims=summary.mixed_or_negative_evidence,
            empty_message="No mixed or negative evidence was found.",
        ),
        SummarySection(
            title="Evidence quality and gaps",
            claims=summary.evidence_quality_and_gaps,
            empty_message="No evidence quality notes were generated.",
        ),
    ]
