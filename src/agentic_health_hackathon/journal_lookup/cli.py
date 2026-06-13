"""Typer CLI for journal lookup."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console
from rich.markdown import Markdown

from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import ProblemProfile
from agentic_health_hackathon.journal_lookup.service import JournalLookupService
from agentic_health_hackathon.logging_utils import configure_logging

app = typer.Typer(
    help="Lookup biomedical literature for supported conditions or free-text questions."
)
console = Console()


def _run_lookup(*, profile: ProblemProfile, verbose: bool, as_json: bool) -> None:
    settings = JournalLookupSettings.from_env()
    logger = configure_logging(verbose=verbose)
    service = JournalLookupService(settings=settings, logger=logger)
    try:
        summary = service.lookup(profile)
        rendered = service.summarizer.render(summary)
    except ValueError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        raise typer.Exit(code=1) from exc
    finally:
        service.close()

    if as_json:
        console.print_json(json.dumps(rendered.summary.model_dump(mode="json"), indent=2))
        return
    console.print(Markdown(rendered.markdown))


@app.command()
def concepts(
    problem: Annotated[
        list[str], typer.Option("--problem", help="Supported concept slug or alias.")
    ],
    max_results: Annotated[int, typer.Option("--max-results", min=1, max=50)] = 12,
    start_year: Annotated[int, typer.Option("--start-year", min=1900, max=3000)] = 2000,
    end_year: Annotated[int, typer.Option("--end-year", min=1900, max=3000)] = 3000,
    include_similar_articles: Annotated[
        bool, typer.Option("--include-similar-articles/--no-include-similar-articles")
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lookup literature for canonical conditions."""
    profile = ProblemProfile(
        canonical_concepts=problem,
        max_results=max_results,
        start_year=start_year,
        end_year=end_year,
        include_similar_articles=include_similar_articles,
    )
    _run_lookup(profile=profile, verbose=verbose, as_json=as_json)


@app.command()
def query(
    text: Annotated[str, typer.Option("--text", help="Free-text literature query.")],
    max_results: Annotated[int, typer.Option("--max-results", min=1, max=50)] = 12,
    start_year: Annotated[int, typer.Option("--start-year", min=1900, max=3000)] = 2000,
    end_year: Annotated[int, typer.Option("--end-year", min=1900, max=3000)] = 3000,
    include_similar_articles: Annotated[
        bool, typer.Option("--include-similar-articles/--no-include-similar-articles")
    ] = True,
    verbose: Annotated[bool, typer.Option("--verbose")] = False,
    as_json: Annotated[bool, typer.Option("--json")] = False,
) -> None:
    """Lookup literature for a free-text biomedical question."""
    profile = ProblemProfile(
        free_text_query=text,
        max_results=max_results,
        start_year=start_year,
        end_year=end_year,
        include_similar_articles=include_similar_articles,
    )
    _run_lookup(profile=profile, verbose=verbose, as_json=as_json)


if __name__ == "__main__":
    app()
