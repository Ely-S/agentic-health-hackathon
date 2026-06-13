from agentic_health_hackathon.journal_lookup.models import (
    CanonicalConcept,
    EvidenceClaim,
    EvidenceSummary,
    PlannedQuery,
    ProblemProfile,
    SearchPlan,
)
from agentic_health_hackathon.journal_lookup.presenter import (
    build_summary_sections,
    supported_problem_options,
)


def test_supported_problem_options_include_me_cfs() -> None:
    options = supported_problem_options()
    assert ("me_cfs", "ME/CFS") in options


def test_build_summary_sections_orders_recommendations_first() -> None:
    concept = CanonicalConcept(
        slug="pots",
        display_name="POTS",
        source_fields=["conditions"],
        aliases=["pots"],
        mesh_terms=["Postural Orthostatic Tachycardia Syndrome"],
        query_terms=["POTS"],
    )
    search_plan = SearchPlan(
        profile=ProblemProfile(canonical_concepts=["pots"]),
        matched_concepts=[concept],
        exact_search_string="pots query",
        planned_queries=[PlannedQuery(stage="broad", query="pots query", limit=5)],
    )
    summary = EvidenceSummary(
        query_plan=search_plan,
        disclaimer="not medical advice",
        what_the_literature_says=[
            EvidenceClaim(
                section="what_the_literature_says",
                text="overview",
                citation_ids=["PMID:1"],
            )
        ],
        interventions_with_positive_signal=[
            EvidenceClaim(
                section="interventions_with_positive_signal",
                text="recommendation",
                citation_ids=["PMID:2"],
            )
        ],
    )
    sections = build_summary_sections(summary)
    assert [section.title for section in sections] == [
        "What the literature says",
        "Interventions with positive signal",
        "Mixed or negative evidence",
        "Evidence quality and gaps",
    ]
