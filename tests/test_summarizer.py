from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    CitationRecord,
    ProblemProfile,
)
from agentic_health_hackathon.journal_lookup.query_planner import QueryPlanner
from agentic_health_hackathon.journal_lookup.summarizer import DeterministicSummarizer


def _article(
    *,
    pmid: str,
    title: str,
    abstract: str,
    evidence_type: str = "trial",
    publication_types: list[str] | None = None,
) -> ArticleHit:
    return ArticleHit(
        citation=CitationRecord(
            citation_id=f"PMID:{pmid}",
            pmid=pmid,
            doi=f"10.1000/{pmid}",
            title=title,
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            journal="Journal",
            publication_year=2024,
            evidence_type=evidence_type,
        ),
        abstract=abstract,
        publication_types=publication_types or ["Clinical Trial"],
        source_databases=["pubmed"],
    )


def test_summary_sections_keep_citations_attached() -> None:
    planner = QueryPlanner()
    plan = planner.create_plan(ProblemProfile(canonical_concepts=["pots"]))
    summarizer = DeterministicSummarizer()
    summary = summarizer.summarize(
        plan=plan,
        articles=[
            _article(
                pmid="1",
                title="Ketotifen improved orthostatic symptoms in POTS",
                abstract="Participants improved with ketotifen and reported benefit.",
            ),
            _article(
                pmid="2",
                title="Famotidine showed mixed results in POTS",
                abstract="Mixed results with no significant difference in the primary outcome.",
            ),
        ],
    )
    assert summary.interventions_with_positive_signal
    assert summary.mixed_or_negative_evidence
    for claim in (
        summary.what_the_literature_says
        + summary.interventions_with_positive_signal
        + summary.mixed_or_negative_evidence
        + summary.evidence_quality_and_gaps
    ):
        assert claim.citation_ids


def test_summary_disclaimer_mentions_not_medical_advice() -> None:
    planner = QueryPlanner()
    plan = planner.create_plan(ProblemProfile(free_text_query="small fiber neuropathy treatment"))
    summarizer = DeterministicSummarizer()
    summary = summarizer.summarize(plan=plan, articles=[])
    assert "not medical advice" in summary.disclaimer.lower()
