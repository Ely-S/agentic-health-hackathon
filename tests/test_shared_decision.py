from pathlib import Path

from agentic_health_hackathon.shared_decision.logit import LogitCoefficientStore
from agentic_health_hackathon.shared_decision.models import PatientIntake
from agentic_health_hackathon.shared_decision.orchestrator import SharedDecisionSupportService
from agentic_health_hackathon.shared_decision.stepping import build_feature_vector, build_step_plan


def test_feature_vector_maps_direct_and_text_features() -> None:
    intake = PatientIntake(
        condition_slugs=["pots"],
        symptoms=["Delayed crashes after activity", "burning and tingling"],
        functional_severity="housebound",
        already_tried_treatments=["antihistamine"],
    )

    vector = build_feature_vector(intake)

    assert vector.features["conditions=pots"] == 1
    assert vector.features["conditions=pem"] == 1
    assert vector.features["conditions=small_fiber_neuropathy"] == 1
    assert vector.features["functional_status_tier=housebound"] == 1
    assert vector.features["func_housebound"] == 1
    assert "not used for similarity" in vector.warnings[0]


def test_step_plan_asks_only_missing_anchor_questions() -> None:
    plan = build_step_plan(PatientIntake(condition_slugs=["pots", "mcas"]))

    step_ids = [step.step_id for step in plan.recommended_steps]

    assert "orthostatic" not in step_ids
    assert "mast_cell" not in step_ids
    assert "pem" in step_ids


def test_logit_store_scores_coefficients(tmp_path: Path) -> None:
    coefficient_path = tmp_path / "drug_logit_coefficients.csv"
    coefficient_path.write_text(
        "\n".join(
            [
                "group,predictor,OR,ci_lo,ci_hi,p,coef,n",
                "LDN/immunomodulator,const,,,,,-1.0,120",
                "LDN/immunomodulator,fibromyalgia,5.0,1.2,12.0,0.01,1.6,120",
                "LDN/immunomodulator,nfields_z,,,,,0.2,120",
            ]
        ),
        encoding="utf-8",
    )
    store = LogitCoefficientStore.from_csv(coefficient_path)
    vector = build_feature_vector(PatientIntake(condition_slugs=["fibromyalgia"]))

    estimate = store.score(treatment_group="LDN/immunomodulator", vector=vector)

    assert estimate.probability_helped is not None
    assert estimate.probability_helped > 0.5
    assert estimate.contributions[0].predictor == "fibromyalgia"
    assert "nfields_z was unavailable" in " ".join(estimate.caveats)


def test_orchestrator_reports_missing_private_backends(tmp_path: Path) -> None:
    coefficient_path = tmp_path / "drug_logit_coefficients.csv"
    coefficient_path.write_text(
        "\n".join(
            [
                "group,predictor,OR,ci_lo,ci_hi,p,coef,n",
                "LDN/immunomodulator,const,,,,,-1.0,120",
                "LDN/immunomodulator,fibromyalgia,5.0,1.2,12.0,0.01,1.6,120",
            ]
        ),
        encoding="utf-8",
    )
    service = SharedDecisionSupportService(
        logit_store=LogitCoefficientStore.from_csv(coefficient_path)
    )

    result = service.prepare(
        PatientIntake(condition_slugs=["fibromyalgia"]),
        candidate_treatment_groups=["LDN/immunomodulator"],
    )

    assert result.treatment_options[0].logit_estimate is not None
    assert result.treatment_options[0].posture == "discuss"
    assert [item.capability for item in result.missing_capabilities] == [
        "patient nearest-neighbor retrieval"
    ]
