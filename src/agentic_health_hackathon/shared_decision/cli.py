"""Typer CLI for shared-decision scaffolding."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console
from rich.table import Table

from agentic_health_hackathon.shared_decision.logit import LogitCoefficientStore
from agentic_health_hackathon.shared_decision.models import PatientIntake, QuestionStep
from agentic_health_hackathon.shared_decision.orchestrator import SharedDecisionSupportService

app = typer.Typer(
    help="Prepare stepped shared-decision scaffolds without loading private patient data."
)
console = Console()


@app.callback()
def main() -> None:
    """Prepare shared-decision evidence scaffolds."""


@app.command()
def plan(
    condition: Annotated[
        list[str] | None,
        typer.Option("--condition", help="Canonical condition slug such as pots or mcas."),
    ] = None,
    symptom: Annotated[
        list[str] | None,
        typer.Option("--symptom", help="Patient-reported symptom text."),
    ] = None,
    diagnosis: Annotated[
        list[str] | None,
        typer.Option("--diagnosis", help="Patient-reported diagnosis text."),
    ] = None,
    severity: Annotated[
        str | None,
        typer.Option("--severity", help="Functional severity such as housebound or severe."),
    ] = None,
    tried: Annotated[
        list[str] | None,
        typer.Option(
            "--tried",
            help="Already-tried treatment. Used for filtering, not similarity.",
        ),
    ] = None,
    treatment_group: Annotated[
        list[str] | None,
        typer.Option(
            "--treatment-group",
            help="Candidate treatment group to score if logits exist.",
        ),
    ] = None,
    coefficients: Annotated[
        Path | None,
        typer.Option("--coefficients", exists=True, file_okay=True, dir_okay=False),
    ] = None,
    include_literature: Annotated[
        bool,
        typer.Option(
            "--include-literature/--no-include-literature",
            help="Request literature lookup if a backend is supplied.",
        ),
    ] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Create the stepped intake and evidence scaffold."""
    logit_store = LogitCoefficientStore.from_csv(coefficients) if coefficients else None
    intake = PatientIntake(
        symptoms=symptom or [],
        diagnoses=diagnosis or [],
        condition_slugs=condition or [],
        functional_severity=severity,
        already_tried_treatments=tried or [],
    )
    service = SharedDecisionSupportService(logit_store=logit_store)
    result = service.prepare(
        intake,
        candidate_treatment_groups=treatment_group or [],
        include_literature=include_literature,
    )
    if as_json:
        console.print_json(json.dumps(result.model_dump(mode="json"), indent=2))
        return

    console.print("[bold]Shared-decision scaffold[/bold]")
    console.print(result.safety.disclaimer)
    console.print()
    _print_features(result.step_plan.feature_vector.features)
    _print_steps(result.step_plan.recommended_steps)
    _print_missing([item.capability for item in result.missing_capabilities])


def _print_features(features: dict[str, float]) -> None:
    table = Table(title="Mapped Features")
    table.add_column("Feature")
    table.add_column("Value")
    for feature, value in sorted(features.items()):
        table.add_row(feature, f"{value:g}")
    if not features:
        table.add_row("(none yet)", "")
    console.print(table)


def _print_steps(steps: list[QuestionStep]) -> None:
    table = Table(title="Recommended Next Questions")
    table.add_column("Step")
    table.add_column("Question")
    for step in steps:
        table.add_row(step.step_id, step.prompt)
    console.print(table)


def _print_missing(capabilities: list[str]) -> None:
    if not capabilities:
        return
    table = Table(title="Missing Backends")
    table.add_column("Capability")
    for capability in capabilities:
        table.add_row(capability)
    console.print(table)


if __name__ == "__main__":
    app()
