"""OpenAlex metadata enrichment."""

from __future__ import annotations

from urllib.parse import quote

from agentic_health_hackathon.journal_lookup.clients.base import CachedHttpClient
from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings

OPENALEX_URL = "https://api.openalex.org/works"


class OpenAlexClient(CachedHttpClient):
    """Fetch citation counts and OA metadata from OpenAlex."""

    def __init__(self, settings: JournalLookupSettings) -> None:
        super().__init__(settings)

    def enrich_by_doi(self, doi: str) -> dict[str, object]:
        """Fetch OpenAlex work metadata for a DOI."""
        headers: dict[str, str] | None = None
        if self.settings.openalex_email:
            headers = {"mailto": self.settings.openalex_email}
        payload = self.get_json(
            namespace="openalex",
            url=f"{OPENALEX_URL}/https://doi.org/{quote(doi, safe='')}",
            params={},
            headers=headers,
        )
        if not isinstance(payload, dict):
            return {}
        return {
            "citation_count": payload.get("cited_by_count"),
            "open_access_url": payload.get("open_access", {}).get("oa_url"),
        }
