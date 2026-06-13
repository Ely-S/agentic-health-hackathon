"""Journal lookup orchestration service."""

from __future__ import annotations

import logging

from agentic_health_hackathon.journal_lookup.clients.crossref import CrossrefClient
from agentic_health_hackathon.journal_lookup.clients.europe_pmc import EuropePmcClient
from agentic_health_hackathon.journal_lookup.clients.openalex import OpenAlexClient
from agentic_health_hackathon.journal_lookup.clients.pubmed import PubMedClient
from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    EvidenceSummary,
    ProblemProfile,
    SearchPlan,
)
from agentic_health_hackathon.journal_lookup.query_planner import QueryPlanner
from agentic_health_hackathon.journal_lookup.summarizer import (
    DeterministicSummarizer,
    strip_crossref_tags,
)
from agentic_health_hackathon.logging_utils import log_phase, new_run_id


class JournalLookupService:
    """End-to-end literature lookup and summarization service."""

    def __init__(
        self,
        *,
        settings: JournalLookupSettings,
        logger: logging.Logger,
        query_planner: QueryPlanner | None = None,
        pubmed_client: PubMedClient | None = None,
        europe_pmc_client: EuropePmcClient | None = None,
        openalex_client: OpenAlexClient | None = None,
        crossref_client: CrossrefClient | None = None,
        summarizer: DeterministicSummarizer | None = None,
    ) -> None:
        self.settings = settings
        self.logger = logger
        self.query_planner = query_planner or QueryPlanner()
        self.pubmed_client = pubmed_client or PubMedClient(settings)
        self.europe_pmc_client = europe_pmc_client or EuropePmcClient(settings)
        self.openalex_client = openalex_client or OpenAlexClient(settings)
        self.crossref_client = crossref_client or CrossrefClient(settings)
        self.summarizer = summarizer or DeterministicSummarizer()

    def close(self) -> None:
        """Close all owned clients."""
        self.pubmed_client.close()
        self.europe_pmc_client.close()
        self.openalex_client.close()
        self.crossref_client.close()

    def lookup(self, profile: ProblemProfile) -> EvidenceSummary:
        """Run the lookup pipeline for a validated problem profile."""
        run_id = new_run_id()
        with log_phase(self.logger, run_id=run_id, phase="plan"):
            plan = self.query_planner.create_plan(profile)

        with log_phase(self.logger, run_id=run_id, phase="retrieve"):
            articles = self._retrieve_articles(plan)

        with log_phase(self.logger, run_id=run_id, phase="summarize"):
            return self.summarizer.summarize(plan=plan, articles=articles)

    def _retrieve_articles(self, plan: SearchPlan) -> list[ArticleHit]:
        pmids: list[str] = []
        for query in plan.planned_queries:
            pmids.extend(self.pubmed_client.search(query.query, limit=query.limit))

        pmids = list(dict.fromkeys(pmid for pmid in pmids if pmid))
        articles = self.pubmed_client.fetch_articles(pmids)
        if not articles:
            return []
        if len(articles) < plan.profile.max_results and plan.profile.include_similar_articles:
            lead_article = articles[0]
            if lead_article.citation.pmid:
                similar_ids = self.pubmed_client.similar_articles(
                    lead_article.citation.pmid,
                    limit=max(0, plan.profile.max_results - len(articles)),
                )
                similar_ids = [pmid for pmid in similar_ids if pmid not in pmids]
                if similar_ids:
                    articles.extend(self.pubmed_client.fetch_articles(similar_ids))

        deduped_articles = self._dedupe_articles(articles)
        enriched_articles = [self._enrich_article(article) for article in deduped_articles]
        for article in enriched_articles:
            article.relevance_score = self.query_planner.score_article(article, plan)
        enriched_articles.sort(key=lambda item: item.relevance_score, reverse=True)
        return enriched_articles[: plan.profile.max_results]

    def _enrich_article(self, article: ArticleHit) -> ArticleHit:
        article = self.europe_pmc_client.enrich(article)
        doi = article.citation.doi
        if not doi:
            return article
        try:
            openalex_metadata = self.openalex_client.enrich_by_doi(doi)
            citation_count = openalex_metadata.get("citation_count")
            if article.citation_count is None and isinstance(citation_count, int):
                article.citation_count = citation_count
            open_access_url = openalex_metadata.get("open_access_url")
            if not article.full_text_url and isinstance(open_access_url, str):
                article.full_text_url = open_access_url
                article.open_access = True
            if "openalex" not in article.source_databases:
                article.source_databases.append("openalex")
        except Exception:
            self.logger.warning(
                "openalex_enrichment_failed",
                extra={"phase": "retrieve", "status": "warning", "doi": doi},
            )

        try:
            crossref_metadata = self.crossref_client.enrich_by_doi(doi)
            abstract_value = crossref_metadata.get("abstract")
            if not article.abstract:
                article.abstract = strip_crossref_tags(
                    abstract_value if isinstance(abstract_value, str) else None
                )
            license_urls = crossref_metadata.get("license_urls")
            if (
                not article.full_text_url
                and isinstance(license_urls, list)
                and all(isinstance(url, str) for url in license_urls)
                and license_urls
            ):
                article.full_text_url = license_urls[0]
            if "crossref" not in article.source_databases:
                article.source_databases.append("crossref")
        except Exception:
            self.logger.warning(
                "crossref_enrichment_failed",
                extra={"phase": "retrieve", "status": "warning", "doi": doi},
            )
        return article

    @staticmethod
    def _dedupe_articles(articles: list[ArticleHit]) -> list[ArticleHit]:
        deduped: dict[str, ArticleHit] = {}
        for article in articles:
            key = article.citation.pmid or article.citation.doi or article.citation.citation_id
            existing = deduped.get(key)
            if existing is None or len(article.abstract or "") > len(existing.abstract or ""):
                deduped[key] = article
        return list(deduped.values())
