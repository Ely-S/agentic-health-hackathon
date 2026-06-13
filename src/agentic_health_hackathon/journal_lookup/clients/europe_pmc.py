"""Europe PMC enrichment client."""

from __future__ import annotations

from urllib.parse import quote

from agentic_health_hackathon.journal_lookup.clients.base import CachedHttpClient
from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import ArticleHit

EUROPE_PMC_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"


class EuropePmcClient(CachedHttpClient):
    """Enrich PubMed records with abstract and OA metadata."""

    def __init__(self, settings: JournalLookupSettings) -> None:
        super().__init__(settings)

    def enrich(self, article: ArticleHit) -> ArticleHit:
        """Return an enriched article hit."""
        pmid = article.citation.pmid
        if not pmid:
            return article
        query = f"EXT_ID:{pmid} AND SRC:MED"
        payload = self.get_json(
            namespace="europe_pmc",
            url=EUROPE_PMC_URL,
            params={"query": query, "format": "json", "pageSize": 1, "resultType": "core"},
        )
        if not isinstance(payload, dict):
            return article
        results = payload.get("resultList", {}).get("result", [])
        if not results:
            return article
        result = results[0]
        if not article.abstract and result.get("abstractText"):
            article.abstract = result["abstractText"]
        doi = result.get("doi")
        if doi and not article.citation.doi:
            article.citation.doi = doi
        cited_by_count = result.get("citedByCount")
        if isinstance(cited_by_count, int):
            article.citation_count = cited_by_count
        elif isinstance(cited_by_count, str) and cited_by_count.isdigit():
            article.citation_count = int(cited_by_count)
        if result.get("isOpenAccess") == "Y":
            article.open_access = True
        full_text_url_list = result.get("fullTextUrlList", {}).get("fullTextUrl", [])
        if full_text_url_list:
            first_url = full_text_url_list[0].get("url")
            if first_url:
                article.full_text_url = first_url
                article.open_access = True
        if "europe_pmc" not in article.source_databases:
            article.source_databases.append("europe_pmc")
        return article

    def pmc_oa_url(self, pmcid: str) -> str:
        """Return the PMC article landing page URL."""
        return f"https://pmc.ncbi.nlm.nih.gov/articles/{quote(pmcid)}/"
