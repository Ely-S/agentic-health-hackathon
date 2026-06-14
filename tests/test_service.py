import logging

from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    CitationRecord,
    ProblemProfile,
)
from agentic_health_hackathon.journal_lookup.service import JournalLookupService


class FakePubMedClient:
    def __init__(self) -> None:
        self.search_calls: list[tuple[str, int]] = []
        self.fetch_calls: list[list[str]] = []
        self.similar_calls: list[tuple[str, int]] = []

    def search(self, query: str, *, limit: int) -> list[str]:
        self.search_calls.append((query, limit))
        return ["1", "2"] if "systematic[sb]" not in query else ["2", "3"]

    def fetch_articles(self, pmids: list[str]) -> list[ArticleHit]:
        self.fetch_calls.append(pmids)
        hits = []
        for pmid in pmids:
            hits.append(
                ArticleHit(
                    citation=CitationRecord(
                        citation_id=f"PMID:{pmid}",
                        pmid=pmid,
                        doi="10.1000/shared" if pmid in {"1", "2"} else f"10.1000/{pmid}",
                        title=f"Article {pmid}",
                        url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                        journal="Test Journal",
                        publication_year=2024,
                    ),
                    abstract="Improved outcomes with ketotifen.",
                    publication_types=["Clinical Trial"],
                    source_databases=["pubmed"],
                )
            )
        return hits

    def similar_articles(self, pmid: str, *, limit: int) -> list[str]:
        self.similar_calls.append((pmid, limit))
        return ["4"]

    def close(self) -> None:
        return None


class FakeEuropePmcClient:
    def enrich(self, article: ArticleHit) -> ArticleHit:
        article.open_access = True
        article.source_databases.append("europe_pmc")
        return article

    def close(self) -> None:
        return None


class FakeOpenAlexClient:
    def enrich_by_doi(self, doi: str) -> dict[str, object]:
        return {"citation_count": 12, "open_access_url": f"https://openalex.org/{doi}"}

    def close(self) -> None:
        return None


class FakeCrossrefClient:
    def enrich_by_doi(self, doi: str) -> dict[str, object]:
        return {
            "abstract": "<jats:p>Improved outcomes with ketotifen.</jats:p>",
            "license_urls": [],
        }

    def close(self) -> None:
        return None


def test_service_dedupes_articles_by_identifier() -> None:
    service = JournalLookupService(
        settings=JournalLookupSettings(),
        logger=logging.getLogger("test-service"),
        pubmed_client=FakePubMedClient(),
        europe_pmc_client=FakeEuropePmcClient(),
        openalex_client=FakeOpenAlexClient(),
        crossref_client=FakeCrossrefClient(),
    )
    try:
        summary = service.lookup(ProblemProfile(canonical_concepts=["pots"], max_results=5))
    finally:
        service.close()
    cited_ids = [article.citation.citation_id for article in summary.cited_articles]
    assert len(cited_ids) == len(set(cited_ids))
    assert all(article.citation_count == 12 for article in summary.cited_articles)
    assert all(article.open_access for article in summary.cited_articles)


def test_service_uses_similar_articles_when_results_are_short() -> None:
    pubmed_client = FakePubMedClient()
    service = JournalLookupService(
        settings=JournalLookupSettings(),
        logger=logging.getLogger("test-service"),
        pubmed_client=pubmed_client,
        europe_pmc_client=FakeEuropePmcClient(),
        openalex_client=FakeOpenAlexClient(),
        crossref_client=FakeCrossrefClient(),
    )
    try:
        service.lookup(ProblemProfile(canonical_concepts=["me_cfs"], max_results=5))
    finally:
        service.close()
    assert pubmed_client.similar_calls == [("1", 2)]
