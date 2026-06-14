import pytest

from agentic_health_hackathon.journal_lookup.lexicon import UnsupportedConceptError
from agentic_health_hackathon.journal_lookup.models import ProblemProfile
from agentic_health_hackathon.journal_lookup.query_planner import QueryPlanner


def test_alias_mapping_cfs_to_me_cfs() -> None:
    planner = QueryPlanner()
    plan = planner.create_plan(ProblemProfile(free_text_query="cfs treatment options"))
    assert [concept.slug for concept in plan.matched_concepts] == ["me_cfs"]
    assert "cfs treatment options" not in (plan.residual_free_text or "")


def test_ambiguous_ms_is_rejected() -> None:
    planner = QueryPlanner()
    with pytest.raises(UnsupportedConceptError):
        planner.create_plan(ProblemProfile(canonical_concepts=["ms"]))


def test_mixed_inputs_preserve_nonconcept_terms() -> None:
    planner = QueryPlanner()
    plan = planner.create_plan(ProblemProfile(free_text_query="pots, ketotifen, ebv"))
    assert {concept.slug for concept in plan.matched_concepts} == {"pots", "viral_reactivation_ebv"}
    assert "ketotifen" in (plan.residual_free_text or "")
    assert "Preserved unmatched terms in search: ketotifen" in plan.notes


def test_free_text_fallback_without_known_concepts() -> None:
    planner = QueryPlanner()
    plan = planner.create_plan(
        ProblemProfile(free_text_query="mitochondrial dysfunction treatment")
    )
    assert plan.used_fallback is True
    assert plan.exact_search_string.startswith(
        '"mitochondrial dysfunction treatment"[Title/Abstract]'
    )
