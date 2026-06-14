"""PubMed E-utilities client."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from agentic_health_hackathon.journal_lookup.clients.base import CachedHttpClient
from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import ArticleHit, CitationRecord

PUBMED_BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"


class PubMedClient(CachedHttpClient):
    """Search and fetch PubMed records."""

    def __init__(self, settings: JournalLookupSettings) -> None:
        super().__init__(settings)

    def search(self, query: str, *, limit: int) -> list[str]:
        """Return PMIDs for a query."""
        params = {
            "db": "pubmed",
            "retmode": "json",
            "retmax": limit,
            "sort": "relevance",
            "term": query,
            "tool": self.settings.pubmed_tool,
        }
        if self.settings.pubmed_email:
            params["email"] = self.settings.pubmed_email
        if self.settings.pubmed_api_key:
            params["api_key"] = self.settings.pubmed_api_key
        payload = self.get_json(
            namespace="pubmed_search",
            url=f"{PUBMED_BASE_URL}/esearch.fcgi",
            params=params,
        )
        if not isinstance(payload, dict):
            return []
        return list(payload.get("esearchresult", {}).get("idlist", []))

    def fetch_articles(self, pmids: list[str]) -> list[ArticleHit]:
        """Fetch PubMed metadata and abstracts for PMIDs."""
        if not pmids:
            return []
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
            "tool": self.settings.pubmed_tool,
        }
        if self.settings.pubmed_email:
            params["email"] = self.settings.pubmed_email
        if self.settings.pubmed_api_key:
            params["api_key"] = self.settings.pubmed_api_key
        xml_payload = self.get_text(
            namespace="pubmed_fetch",
            url=f"{PUBMED_BASE_URL}/efetch.fcgi",
            params=params,
        )
        root = ET.fromstring(xml_payload)
        articles: list[ArticleHit] = []
        for article_node in root.findall(".//PubmedArticle"):
            article = article_node.find(".//Article")
            medline = article_node.find(".//MedlineCitation")
            if article is None or medline is None:
                continue
            pmid = (medline.findtext("PMID") or "").strip()
            title = "".join(article.findtext("ArticleTitle") or "").strip()
            journal = article.findtext(".//Journal/Title")
            year_text = (
                article.findtext(".//JournalIssue/PubDate/Year")
                or article.findtext(".//PubDate/MedlineDate")
                or ""
            )
            year = self._parse_year(year_text)
            abstract_parts = [
                "".join(node.itertext()).strip()
                for node in article.findall(".//Abstract/AbstractText")
                if "".join(node.itertext()).strip()
            ]
            abstract_text = " ".join(abstract_parts) or None
            publication_types = [
                (node.text or "").strip()
                for node in article.findall(".//PublicationTypeList/PublicationType")
                if (node.text or "").strip()
            ]
            mesh_terms = [
                (node.text or "").strip()
                for node in article_node.findall(".//MeshHeading/DescriptorName")
                if (node.text or "").strip()
            ]
            authors = []
            for author_node in article.findall(".//AuthorList/Author"):
                last_name = (author_node.findtext("LastName") or "").strip()
                initials = (author_node.findtext("Initials") or "").strip()
                collective = (author_node.findtext("CollectiveName") or "").strip()
                if collective:
                    authors.append(collective)
                elif last_name:
                    authors.append(f"{last_name} {initials}".strip())

            doi = None
            for article_id in article_node.findall(".//PubmedData/ArticleIdList/ArticleId"):
                if article_id.attrib.get("IdType") == "doi":
                    doi = (article_id.text or "").strip()
                    break

            citation = CitationRecord(
                citation_id=f"PMID:{pmid}",
                title=title,
                url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                journal=journal,
                publication_year=year,
                pmid=pmid or None,
                doi=doi,
                evidence_type=self._infer_evidence_type(publication_types),
            )
            articles.append(
                ArticleHit(
                    citation=citation,
                    abstract=abstract_text,
                    mesh_terms=mesh_terms,
                    publication_types=publication_types,
                    authors=authors,
                    source_databases=["pubmed"],
                )
            )
        return articles

    def similar_articles(self, pmid: str, *, limit: int) -> list[str]:
        """Return similar PubMed PMIDs for a seed article."""
        params = {
            "dbfrom": "pubmed",
            "db": "pubmed",
            "cmd": "neighbor",
            "id": pmid,
            "retmode": "xml",
            "tool": self.settings.pubmed_tool,
        }
        if self.settings.pubmed_email:
            params["email"] = self.settings.pubmed_email
        if self.settings.pubmed_api_key:
            params["api_key"] = self.settings.pubmed_api_key
        xml_payload = self.get_text(
            namespace="pubmed_similar",
            url=f"{PUBMED_BASE_URL}/elink.fcgi",
            params=params,
        )
        root = ET.fromstring(xml_payload)
        similar_ids = [
            (node.text or "").strip()
            for node in root.findall(".//LinkSetDb/Link/Id")
            if (node.text or "").strip()
        ]
        deduped = [candidate for candidate in dict.fromkeys(similar_ids) if candidate != pmid]
        return deduped[:limit]

    @staticmethod
    def _parse_year(raw_value: str) -> int | None:
        for token in raw_value.replace("/", " ").split():
            if token.isdigit() and len(token) == 4:
                return int(token)
        return None

    @staticmethod
    def _infer_evidence_type(publication_types: list[str]) -> str:
        lowered = {value.lower() for value in publication_types}
        if "systematic review" in lowered or "meta-analysis" in lowered:
            return "review"
        if "clinical trial" in lowered or "randomized controlled trial" in lowered:
            return "trial"
        if "observational study" in lowered:
            return "observational"
        return "article"
