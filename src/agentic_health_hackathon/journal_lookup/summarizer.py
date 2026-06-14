"""Deterministic evidence summarization."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from importlib import resources
from typing import Literal

from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    EvidenceClaim,
    EvidenceSummary,
    RenderedSummary,
    SearchPlan,
)

POSITIVE_PATTERNS = (
    "improved",
    "improvement",
    "benefit",
    "effective",
    "efficacy",
    "response",
    "responders",
    "ameliorat",
)
MIXED_OR_NEGATIVE_PATTERNS = (
    "no significant",
    "no difference",
    "mixed",
    "heterogeneous",
    "worsen",
    "adverse",
    "not effective",
    "did not improve",
    "insufficient evidence",
)
TAG_PATTERN = re.compile(r"<[^>]+>")


class DeterministicSummarizer:
    """Create structured claims without relying on a live LLM."""

    def __init__(self) -> None:
        resource_root = resources.files("agentic_health_hackathon.journal_lookup.resources")
        self.template = resource_root.joinpath("evidence_summary.md").read_text(encoding="utf-8")
        interventions_path = resource_root.joinpath("interventions.json")
        self.intervention_terms: list[str] = json.loads(
            interventions_path.read_text(encoding="utf-8")
        )

    def annotate_articles(self, articles: list[ArticleHit]) -> list[ArticleHit]:
        """Apply signal and intervention heuristics to article hits."""
        for article in articles:
            article.signal = self._classify_signal(article)
            article.signal_rationale = self._signal_rationale(article.signal)
            article.matched_interventions = self._extract_interventions(article)
        return articles

    def summarize(self, *, plan: SearchPlan, articles: list[ArticleHit]) -> EvidenceSummary:
        """Build the structured evidence summary."""
        annotated_articles = self.annotate_articles(articles)
        summary = EvidenceSummary(
            query_plan=plan,
            disclaimer=(
                "This summary is for hypothesis generation from published literature. "
                "It is not medical advice and does not replace clinician judgment."
            ),
            what_the_literature_says=self._build_overview_claims(plan, annotated_articles),
            interventions_with_positive_signal=self._build_signal_claims(
                annotated_articles, section="interventions_with_positive_signal", signal="positive"
            ),
            mixed_or_negative_evidence=self._build_signal_claims(
                annotated_articles, section="mixed_or_negative_evidence", signal="mixed_or_negative"
            ),
            evidence_quality_and_gaps=self._build_quality_claims(annotated_articles),
            cited_articles=annotated_articles,
        )
        return summary

    def render(self, summary: EvidenceSummary) -> RenderedSummary:
        """Render markdown output for CLI display."""
        problem_line = ", ".join(
            concept.display_name for concept in summary.query_plan.matched_concepts
        ) or (summary.query_plan.exact_user_query or "free-text search")
        markdown = self.template.format(
            problem_line=problem_line,
            exact_search_string=summary.query_plan.exact_search_string,
            what_the_literature_says=self._render_claims(summary.what_the_literature_says),
            positive_signal=self._render_claims(summary.interventions_with_positive_signal),
            mixed_or_negative=self._render_claims(summary.mixed_or_negative_evidence),
            quality_and_gaps=self._render_claims(summary.evidence_quality_and_gaps),
            cited_articles=self._render_citations(summary.cited_articles),
            disclaimer=summary.disclaimer,
        )
        return RenderedSummary(markdown=markdown, summary=summary)

    def _classify_signal(
        self, article: ArticleHit
    ) -> Literal["positive", "mixed_or_negative", "neutral", "insufficient"]:
        body = f"{article.citation.title} {article.abstract or ''}".lower()
        positive = any(pattern in body for pattern in POSITIVE_PATTERNS)
        mixed_or_negative = any(pattern in body for pattern in MIXED_OR_NEGATIVE_PATTERNS)
        if positive and not mixed_or_negative:
            return "positive"
        if mixed_or_negative:
            return "mixed_or_negative"
        if article.abstract:
            return "neutral"
        return "insufficient"

    @staticmethod
    def _signal_rationale(signal: str) -> str:
        rationales = {
            "positive": "Benefit-oriented language appears in the title or abstract.",
            "mixed_or_negative": (
                "The article contains mixed, negative, or insufficient-evidence language."
            ),
            "neutral": "The article discusses the topic without a clear intervention signal.",
            "insufficient": "No abstract or clear signal was available.",
        }
        return rationales[signal]

    def _extract_interventions(self, article: ArticleHit) -> list[str]:
        haystack = f"{article.citation.title} {article.abstract or ''}".lower()
        matches = [
            term
            for term in self.intervention_terms
            if re.search(rf"(?<!\w){re.escape(term)}(?!\w)", haystack)
        ]
        return list(dict.fromkeys(matches))

    def _build_overview_claims(
        self, plan: SearchPlan, articles: list[ArticleHit]
    ) -> list[EvidenceClaim]:
        claims: list[EvidenceClaim] = []
        for article in articles[:3]:
            year = article.citation.publication_year or "n.d."
            evidence_type = article.citation.evidence_type or "article"
            journal = article.citation.journal or "an indexed journal"
            text = (
                f"{year} {evidence_type} evidence in {journal} "
                f"addresses {self._problem_label(plan)} through '{article.citation.title}'."
            )
            claims.append(
                EvidenceClaim(
                    section="what_the_literature_says",
                    text=text,
                    citation_ids=[article.citation.citation_id],
                )
            )
        if not claims:
            claims.append(
                EvidenceClaim(
                    section="what_the_literature_says",
                    text="No matching literature hits were retrieved for the current search plan.",
                    citation_ids=["search-plan"],
                )
            )
        return claims

    def _build_signal_claims(
        self,
        articles: list[ArticleHit],
        *,
        section: Literal[
            "interventions_with_positive_signal",
            "mixed_or_negative_evidence",
        ],
        signal: Literal["positive", "mixed_or_negative"],
    ) -> list[EvidenceClaim]:
        grouped: dict[str, list[str]] = defaultdict(list)
        fallback_claims: list[EvidenceClaim] = []
        for article in articles:
            if article.signal != signal:
                continue
            if article.matched_interventions:
                for intervention in article.matched_interventions:
                    grouped[intervention].append(article.citation.citation_id)
            else:
                fallback_claims.append(
                    EvidenceClaim(
                        section=section,
                        text=(
                            f"{article.citation.title} is categorized as "
                            f"{signal.replace('_', ' ')} evidence."
                        ),
                        citation_ids=[article.citation.citation_id],
                    )
                )

        claims: list[EvidenceClaim] = []
        for intervention, citations in sorted(
            grouped.items(), key=lambda item: (-len(item[1]), item[0])
        )[:5]:
            text = (
                f"{intervention} appears in {len(citations)} {signal.replace('_', ' ')} "
                f"article(s) in the retrieved set."
            )
            claims.append(
                EvidenceClaim(section=section, text=text, citation_ids=sorted(set(citations)))
            )
        if not claims:
            claims.extend(fallback_claims[:3])
        if not claims:
            empty_text = (
                "No positive intervention signal was detected in the retrieved literature."
                if signal == "positive"
                else (
                    "No mixed or negative intervention signal was detected "
                    "in the retrieved literature."
                )
            )
            claims.append(
                EvidenceClaim(section=section, text=empty_text, citation_ids=["search-plan"])
            )
        return claims

    def _build_quality_claims(self, articles: list[ArticleHit]) -> list[EvidenceClaim]:
        if not articles:
            return [
                EvidenceClaim(
                    section="evidence_quality_and_gaps",
                    text=(
                        "The search returned no articles, so evidence quality could not "
                        "be assessed."
                    ),
                    citation_ids=["search-plan"],
                )
            ]
        review_count = sum(
            1 for article in articles if (article.citation.evidence_type or "") == "review"
        )
        trial_count = sum(
            1 for article in articles if (article.citation.evidence_type or "") == "trial"
        )
        citations = [article.citation.citation_id for article in articles[:3]]
        claims = [
            EvidenceClaim(
                section="evidence_quality_and_gaps",
                text=(
                    f"The retrieved set includes {review_count} review-style article(s) and "
                    f"{trial_count} trial-style article(s), so conclusions should be "
                    "weighted by study design."
                ),
                citation_ids=citations,
            )
        ]
        if sum(1 for article in articles if article.open_access) < max(1, len(articles) // 3):
            claims.append(
                EvidenceClaim(
                    section="evidence_quality_and_gaps",
                    text=(
                        "Only a minority of the retrieved articles had clear open-access "
                        "full text available."
                    ),
                    citation_ids=citations,
                )
            )
        if all(article.signal == "insufficient" for article in articles):
            claims.append(
                EvidenceClaim(
                    section="evidence_quality_and_gaps",
                    text=(
                        "Most retrieved records lacked abstract detail, so this search "
                        "should be widened or manually reviewed."
                    ),
                    citation_ids=citations,
                )
            )
        return claims

    @staticmethod
    def _problem_label(plan: SearchPlan) -> str:
        if plan.matched_concepts:
            return ", ".join(concept.display_name for concept in plan.matched_concepts)
        return plan.exact_user_query or "the submitted problem set"

    @staticmethod
    def _render_claims(claims: list[EvidenceClaim]) -> str:
        lines = [f"- {claim.text} ({', '.join(claim.citation_ids)})" for claim in claims]
        return "\n".join(lines) if lines else "- None."

    def _render_citations(self, articles: list[ArticleHit]) -> str:
        lines = []
        for article in articles:
            year = article.citation.publication_year or "n.d."
            title = article.citation.title
            journal = article.citation.journal or "Unknown journal"
            url = article.full_text_url or article.citation.url
            lines.append(f"- {article.citation.citation_id}: {title} ({journal}, {year}) [{url}]")
        return "\n".join(lines) if lines else "- None."


def strip_crossref_tags(value: str | None) -> str | None:
    """Remove simple Crossref XML tags from an abstract snippet."""
    if value is None:
        return None
    return TAG_PATTERN.sub("", value).strip() or None
