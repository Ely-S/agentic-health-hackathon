"""
litsearch.py — wrap the journal_lookup package (PubMed / Europe PMC / OpenAlex / Crossref +
deterministic summarizer) as a single REST-friendly call for the UI popup.

The package lives under src/ and isn't installed, so we add it to sys.path lazily. The
JournalLookupService is built once (it holds disk-cached HTTP clients) and reused. Network
failures or empty results degrade to a response with `error` set rather than a 500.
"""
from __future__ import annotations

import sys
import threading
from pathlib import Path

from .models import (
    LitArticle,
    LitClaim,
    LitSearchRequest,
    LitSearchResponse,
    LitSection,
)

# Make the journal_lookup package importable (src/agentic_health_hackathon/...).
_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.exists() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

_service = None
_lock = threading.Lock()


def _get_service():
    global _service
    if _service is None:
        with _lock:
            if _service is None:
                from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
                from agentic_health_hackathon.journal_lookup.service import JournalLookupService
                from agentic_health_hackathon.logging_utils import configure_logging

                settings = JournalLookupSettings.from_env()
                logger = configure_logging(verbose=False)
                _service = JournalLookupService(settings=settings, logger=logger)
    return _service


def lit_search(req: LitSearchRequest) -> LitSearchResponse:
    query = (req.query or "").strip()
    if not query and not req.concepts:
        return LitSearchResponse(query=query, error="Enter a search term.")

    from agentic_health_hackathon.journal_lookup.models import ProblemProfile
    from agentic_health_hackathon.journal_lookup.presenter import build_summary_sections

    try:
        service = _get_service()
        summary = service.lookup(
            ProblemProfile(
                free_text_query=query or None,
                canonical_concepts=list(req.concepts or []),
                max_results=req.max_results,
            )
        )
    except Exception as exc:  # network / parsing / upstream outage
        return LitSearchResponse(
            query=query,
            error=f"Literature sources are unavailable right now ({type(exc).__name__}). Try again shortly.",
        )

    sections = [
        LitSection(
            title=s.title,
            claims=[LitClaim(text=c.text, citation_ids=list(c.citation_ids)) for c in s.claims],
        )
        for s in build_summary_sections(summary)
    ]
    articles = [
        LitArticle(
            citation_id=a.citation.citation_id,
            title=a.citation.title,
            url=a.citation.url,
            journal=a.citation.journal,
            year=a.citation.publication_year,
            pmid=a.citation.pmid,
            doi=a.citation.doi,
            evidence_type=a.citation.evidence_type,
            signal=a.signal,
            citation_count=a.citation_count,
            open_access=a.open_access,
            abstract=(a.abstract or "")[:480],
        )
        for a in summary.cited_articles
    ]
    if not articles:
        return LitSearchResponse(
            query=query, disclaimer=summary.disclaimer, sections=sections, articles=[],
            error="No matching literature was found for that query.",
        )

    llm_summary = _llm_summary(query, articles)
    return LitSearchResponse(
        query=query, disclaimer=summary.disclaimer, sections=sections, articles=articles,
        llm_summary=llm_summary, summary_source="llm" if llm_summary else "deterministic",
    )


def _llm_summary(query: str, articles) -> str | None:
    """Ask the LLM (if a key is configured) to narrate the retrieved evidence. None otherwise."""
    from .evidence import _llm

    lines = []
    for i, a in enumerate(articles[:8], 1):
        sig = {"positive": "positive", "mixed_or_negative": "mixed/negative"}.get(a.signal, "neutral")
        lines.append(
            f"[{i}] ({a.year or 'n.d.'}, {a.evidence_type or 'study'}, signal: {sig}) "
            f"{a.title} — {(a.abstract or '')[:300]}"
        )
    prompt = (
        "You are a careful clinical-evidence assistant for a patient-experience tool. This is NOT "
        f"medical advice. A user searched the literature for: \"{query}\".\n\n"
        "Here are the retrieved papers:\n" + "\n".join(lines) + "\n\n"
        "Write a concise, plain-language evidence summary in 3-5 sentences (or short bullets): what the "
        "literature suggests overall, which interventions show a positive vs mixed/negative signal, and the "
        "main limitations (study type, size, certainty). Reference papers as [1], [2]. Stay grounded in the "
        "excerpts above — do not invent findings, dosing, or recommendations."
    )
    return _llm(prompt, max_tokens=350)
