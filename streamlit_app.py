from __future__ import annotations

import streamlit as st

from agentic_health_hackathon.journal_lookup.config import JournalLookupSettings
from agentic_health_hackathon.journal_lookup.models import (
    ArticleHit,
    EvidenceClaim,
    EvidenceSummary,
    ProblemProfile,
)
from agentic_health_hackathon.journal_lookup.presenter import (
    build_summary_sections,
    supported_problem_options,
)
from agentic_health_hackathon.journal_lookup.service import JournalLookupService
from agentic_health_hackathon.logging_utils import configure_logging

st.set_page_config(
    page_title="Journal Lookup",
    page_icon=":mag:",
    layout="wide",
    initial_sidebar_state="expanded",
)


def inject_styles() -> None:
    """Apply lightweight visual styling for the demo UI."""
    st.markdown(
        """
        <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(219, 234, 254, 0.7), transparent 30%),
                linear-gradient(180deg, #f8fafc 0%, #eef2f7 100%);
        }
        .block-container {
            max-width: 1280px;
            padding-top: 2rem;
            padding-bottom: 3rem;
        }
        .ahh-kpi {
            background: rgba(255, 255, 255, 0.92);
            border: 1px solid rgba(15, 23, 42, 0.08);
            border-radius: 8px;
            padding: 0.85rem 1rem;
            min-height: 92px;
        }
        .ahh-kpi-label {
            font-size: 0.78rem;
            text-transform: uppercase;
            letter-spacing: 0.04em;
            color: #64748b;
            margin-bottom: 0.45rem;
        }
        .ahh-kpi-value {
            font-size: 1.15rem;
            color: #0f172a;
            font-weight: 600;
        }
        .ahh-claim {
            padding: 0.65rem 0.75rem;
            background: #f8fafc;
            border-radius: 6px;
            border: 1px solid rgba(148, 163, 184, 0.18);
            margin-bottom: 0.65rem;
        }
        .ahh-citation {
            color: #475569;
            font-size: 0.85rem;
            margin-top: 0.35rem;
        }
        .ahh-article-title {
            font-weight: 600;
            color: #0f172a;
            margin-bottom: 0.3rem;
        }
        .ahh-article-meta {
            color: #475569;
            font-size: 0.88rem;
            margin-bottom: 0.5rem;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


@st.cache_resource(show_spinner=False)
def get_service() -> JournalLookupService:
    """Create and cache the lookup service for the app session."""
    settings = JournalLookupSettings.from_env()
    logger = configure_logging(verbose=False)
    return JournalLookupService(settings=settings, logger=logger)


def render_claim(claim: EvidenceClaim) -> None:
    """Render a single summary claim."""
    citation_line = ", ".join(claim.citation_ids)
    st.markdown(
        (
            "<div class='ahh-claim'>"
            f"<div>{claim.text}</div>"
            f"<div class='ahh-citation'>Citations: {citation_line}</div>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def render_article(article: ArticleHit) -> None:
    """Render a detailed article card."""
    title = article.citation.title
    journal = article.citation.journal or "Unknown journal"
    year = article.citation.publication_year or "n.d."
    evidence_type = article.citation.evidence_type or "article"
    signal = article.signal.replace("_", " ")
    databases = ", ".join(article.source_databases)
    st.markdown(
        (
            "<div class='ahh-article-title'>"
            f"<a href='{article.full_text_url or article.citation.url}' target='_blank'>{title}</a>"
            "</div>"
            "<div class='ahh-article-meta'>"
            f"{journal} | {year} | {evidence_type} | signal: {signal} | sources: {databases}"
            "</div>"
        ),
        unsafe_allow_html=True,
    )
    if article.abstract:
        st.write(article.abstract)
    article_links: list[str] = [f"[PubMed]({article.citation.url})"]
    if article.full_text_url:
        article_links.append(f"[Open access / full text]({article.full_text_url})")
    if article.citation.doi:
        article_links.append(f"[DOI](https://doi.org/{article.citation.doi})")
    st.caption(" | ".join(article_links))
    if article.matched_interventions:
        st.caption(f"Matched interventions: {', '.join(article.matched_interventions)}")


def render_summary(summary: EvidenceSummary) -> None:
    """Render the summary-first results layout."""
    matched_labels = ", ".join(
        concept.display_name for concept in summary.query_plan.matched_concepts
    ) or "Free-text search"
    top_cols = st.columns(4)
    kpis = [
        ("Matched problems", matched_labels),
        ("Search mode", "Fallback" if summary.query_plan.used_fallback else "Canonical"),
        ("Articles returned", str(len(summary.cited_articles))),
        (
            "Search window",
            f"{summary.query_plan.profile.start_year}-{summary.query_plan.profile.end_year}",
        ),
    ]
    for column, (label, value) in zip(top_cols, kpis, strict=True):
        with column:
            st.markdown(
                (
                    "<div class='ahh-kpi'>"
                    f"<div class='ahh-kpi-label'>{label}</div>"
                    f"<div class='ahh-kpi-value'>{value}</div>"
                    "</div>"
                ),
                unsafe_allow_html=True,
            )

    st.write("")
    left, right = st.columns((1.5, 1), gap="large")
    sections = build_summary_sections(summary)

    with left:
        for section in sections[:2]:
            st.markdown(f"### {section.title}")
            if section.claims:
                for claim in section.claims:
                    render_claim(claim)
            else:
                st.info(section.empty_message)

    with right:
        for section in sections[2:]:
            st.markdown(f"### {section.title}")
            if section.claims:
                for claim in section.claims:
                    render_claim(claim)
            else:
                st.info(section.empty_message)

    st.write("")
    with st.expander("Search details", expanded=False):
        st.code(summary.query_plan.exact_search_string, language="text")
        if summary.query_plan.notes:
            for note in summary.query_plan.notes:
                st.caption(note)
        st.caption(summary.disclaimer)

    st.markdown("### Articles")
    if not summary.cited_articles:
        st.warning("No articles were returned for this query.")
        return
    for article in summary.cited_articles:
        with st.container(border=True):
            render_article(article)


def main() -> None:
    """Run the Streamlit app."""
    inject_styles()
    st.title("Journal Lookup")
    st.caption(
        "Literature-first journal search for supported conditions and free-text questions."
    )

    problem_options = supported_problem_options()
    option_map = {label: slug for slug, label in problem_options}

    with st.sidebar:
        st.header("Query")
        selected_labels = st.multiselect(
            "Supported problems",
            options=[label for _, label in problem_options],
            default=["ME/CFS"],
            help="Choose one or more supported canonical problems.",
        )
        free_text_query = st.text_area(
            "Free-text query",
            value="",
            placeholder="small fiber neuropathy and long covid treatment",
            help="Use this for raw literature search terms or extra qualifiers.",
        )
        max_results = st.slider("Max articles", min_value=3, max_value=20, value=8, step=1)
        year_range = st.slider(
            "Publication years",
            min_value=1990,
            max_value=2026,
            value=(2020, 2025),
        )
        include_similar = st.checkbox("Expand via similar articles", value=True)
        submitted = st.button("Run lookup", type="primary", use_container_width=True)

    if not submitted:
        st.info("Choose a supported problem or enter a free-text search, then run the lookup.")
        return

    canonical_concepts = [option_map[label] for label in selected_labels]
    try:
        profile = ProblemProfile(
            canonical_concepts=canonical_concepts,
            free_text_query=free_text_query or None,
            max_results=max_results,
            start_year=year_range[0],
            end_year=year_range[1],
            include_similar_articles=include_similar,
        )
    except ValueError as exc:
        st.error(str(exc))
        return

    service = get_service()
    with st.spinner("Searching PubMed and enriching results..."):
        try:
            summary = service.lookup(profile)
        except ValueError as exc:
            st.error(str(exc))
            return
        except Exception as exc:  # pragma: no cover - network/runtime handling
            st.exception(exc)
            return
    render_summary(summary)


if __name__ == "__main__":
    main()
