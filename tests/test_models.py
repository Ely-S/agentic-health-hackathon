from agentic_health_hackathon.journal_lookup.models import (
    CanonicalConcept,
    EvidenceClaim,
    EvidenceSummary,
    PlannedQuery,
    ProblemProfile,
    SearchPlan,
)


def test_problem_profile_requires_input() -> None:
    try:
        ProblemProfile()
    except ValueError as exc:
        assert "Provide at least one canonical concept" in str(exc)
    else:
        raise AssertionError("ProblemProfile should reject empty input.")


def test_evidence_summary_round_trip() -> None:
    concept = CanonicalConcept(
        slug="me_cfs",
        display_name="ME/CFS",
        source_fields=["conditions"],
        aliases=["cfs"],
        mesh_terms=["Fatigue Syndrome, Chronic"],
        query_terms=["ME/CFS"],
    )
    profile = ProblemProfile(canonical_concepts=["me_cfs"])
    search_plan = SearchPlan(
        profile=profile,
        matched_concepts=[concept],
        exact_search_string='("ME/CFS"[Title/Abstract]) AND humans[mh]',
        planned_queries=[PlannedQuery(stage="broad", query="foo", limit=5)],
    )
    summary = EvidenceSummary(
        query_plan=search_plan,
        disclaimer="not medical advice",
        what_the_literature_says=[
            EvidenceClaim(
                section="what_the_literature_says",
                text="Example claim",
                citation_ids=["PMID:1"],
            )
        ],
    )
    dumped = summary.model_dump(mode="json")
    loaded = EvidenceSummary.model_validate(dumped)
    assert loaded.query_plan.matched_concepts[0].slug == "me_cfs"
