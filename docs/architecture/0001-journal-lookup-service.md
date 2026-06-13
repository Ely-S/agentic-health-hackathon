# ADR 0001: Journal Lookup Service Shape

## Status
Accepted

## Context
The repository did not yet have application code, but the journal lookup workstream needs a
production-shaped skeleton instead of another ad hoc script. The service must stay separate
from the patient-evidence workstream, use structured boundary models, and keep downloaded
literature artifacts out of git.

## Decision
- Build the feature as a Python package under `src/` with a thin Typer CLI entry point.
- Use Pydantic v2 models for request, query plan, article hit, citation, and summary
  artifacts.
- Use PubMed E-utilities as the primary search authority.
- Use Europe PMC for abstract and open-access enrichment, and OpenAlex and Crossref only for
  metadata enrichment.
- Default to deterministic summarization with a clean replacement point for a later live LLM.
- Keep cache data outside the repository in a user-level cache directory.

## Consequences
- The first version is immediately testable and does not depend on a model provider.
- Summary quality is bounded by heuristics until a live summarizer is added.
- The CLI and data models are stable enough for a future UI or orchestration layer to call
  directly.
