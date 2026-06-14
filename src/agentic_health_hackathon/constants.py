"""Shared application constants."""

from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "agentic-health-hackathon"
SCHEMA_ID = "journal_lookup.v1"
PACKAGE_ROOT = Path(__file__).resolve().parent


def default_cache_dir() -> Path:
    """Return the writable cache directory used for remote metadata."""
    if override := os.environ.get("AHH_CACHE_DIR"):
        return Path(override).expanduser().resolve()
    local_app_data = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        return Path(local_app_data) / APP_NAME / "cache" / "journal_lookup"
    return Path.home() / ".cache" / APP_NAME / "journal_lookup"
