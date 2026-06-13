"""Configuration for the journal lookup service."""

from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, Field, field_validator

from agentic_health_hackathon.constants import default_cache_dir


class JournalLookupSettings(BaseModel):
    """Runtime settings for CLI and API clients."""

    cache_dir: Path = Field(default_factory=default_cache_dir)
    http_timeout_seconds: float = 20.0
    default_max_results: int = 12
    default_start_year: int = 2000
    default_end_year: int = 3000
    pubmed_tool: str = "agentic-health-hackathon"
    pubmed_email: str | None = None
    user_agent: str = "agentic-health-hackathon/0.1.0"
    openalex_email: str | None = None
    crossref_mailto: str | None = None

    @field_validator("cache_dir")
    @classmethod
    def _expand_cache_dir(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @classmethod
    def from_env(cls) -> JournalLookupSettings:
        """Build settings from environment variables."""
        cache_override = os.environ.get("AHH_CACHE_DIR")
        cache_dir = Path(cache_override) if cache_override else default_cache_dir()
        http_timeout_seconds = float(os.environ.get("AHH_HTTP_TIMEOUT_SECONDS", "20.0"))
        default_max_results = int(os.environ.get("AHH_DEFAULT_MAX_RESULTS", "12"))
        default_start_year = int(os.environ.get("AHH_DEFAULT_START_YEAR", "2000"))
        return cls(
            cache_dir=cache_dir,
            http_timeout_seconds=http_timeout_seconds,
            default_max_results=default_max_results,
            default_start_year=default_start_year,
            pubmed_email=os.environ.get("PUBMED_EMAIL"),
            openalex_email=os.environ.get("OPENALEX_EMAIL"),
            crossref_mailto=os.environ.get("CROSSREF_MAILTO"),
        )
