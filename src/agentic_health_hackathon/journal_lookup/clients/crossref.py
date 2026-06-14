"""Crossref DOI metadata client."""

from __future__ import annotations

from urllib.parse import quote

from agentic_health_hackathon.journal_lookup.clients.base import CachedHttpClient
from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings

CROSSREF_URL = "https://api.crossref.org/works"


class CrossrefClient(CachedHttpClient):
    """Fetch DOI metadata and licensing information."""

    def __init__(self, settings: JournalLookupSettings) -> None:
        super().__init__(settings)

    def enrich_by_doi(self, doi: str) -> dict[str, object]:
        """Fetch Crossref metadata for a DOI."""
        headers: dict[str, str] | None = None
        if self.settings.crossref_mailto:
            headers = {"mailto": self.settings.crossref_mailto}
        payload = self.get_json(
            namespace="crossref",
            url=f"{CROSSREF_URL}/{quote(doi, safe='')}",
            params={},
            headers=headers,
        )
        if not isinstance(payload, dict):
            return {}
        message = payload.get("message", {})
        licenses = message.get("license", [])
        return {
            "abstract": message.get("abstract"),
            "license_urls": [entry.get("URL") for entry in licenses if entry.get("URL")],
        }
