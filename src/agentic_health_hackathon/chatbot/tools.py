"""The DashboardChatbot's tools — thin wrappers over ``ChatbotQueryService``.

Each is a ``@tool(["DashboardChatbot"])`` sync free function with PRIMITIVE
params only (``list[str]`` / ``str``) and returns a formatted STRING that embeds
the raw numbers (Rumi forbids response_model + tools, so the model reads the
figures out of the string and cites them). The one-line docstring is the tool's
description the LLM sees.

Cohort-backed tools return an explicit "no similar-patient cohort is available in
this dataset" string when ``matched_patients == 0`` — the conditions table is
sparse in both available DBs, so this is the honest, common case.

IMPORTANT: importing this module registers the tools globally (Rumi's @tool
registry). ``agent.py`` imports it at module top so the tools exist BEFORE the
Dervish is constructed.
"""

from __future__ import annotations

from backend.search_api.chatbot import ChatbotQueryService
from backend.search_api.models import TreatmentPrediction
from rumi import tool

_SVC = ChatbotQueryService()

_NO_COHORT = (
    "No similar-patient cohort is available in this dataset for that profile "
    "(the conditions table is sparse here, so cohort and 'patients like me' "
    "questions cannot be answered from data). The prediction, explanation, and "
    "literature tools still work."
)


def _fmt_pred(p: TreatmentPrediction) -> str:
    """One prediction → a fully-cited line."""
    return (
        f"{p.category}: {p.p_positive}% positive (95% CI {p.ci_lo}-{p.ci_hi}%), "
        f"n={p.n}, confidence={p.confidence}, baseline={p.baseline}% "
        f"(delta {p.delta:+d}pp){', drivers: ' + ', '.join(p.drivers) if p.drivers else ''}"
    )


@tool(["DashboardChatbot"])
def get_prediction(conditions: list[str], severity: str) -> str:
    """Per-class predicted % positive (95% CI, n, baseline, drivers) for this profile."""
    resp = _SVC.predict(list(conditions), severity or None)
    prof = ", ".join(resp.profile) if resp.profile else "(baseline population — none selected)"
    lines = [_fmt_pred(p) for p in resp.predictions]
    return (
        f"Profile: {prof}.\n"
        "Predicted chance of a POSITIVE experience per drug class (logistic model on "
        "self-reported outcomes):\n- " + "\n- ".join(lines) + f"\n\nDisclaimer: {resp.disclaimer}"
    )


@tool(["DashboardChatbot"])
def get_treatment_evidence(conditions: list[str], severity: str) -> str:
    """Similar-patient cohort size + quoteable reports + real positive quotes per class for this profile."""  # noqa: E501
    resp = _SVC.treatment_evidence(list(conditions), severity or None)
    if resp is None:
        return "Cohort evidence is unavailable right now (the patient dataset could not be read)."
    if resp.matched_patients == 0:
        return _NO_COHORT
    parts = [
        f"Similar-patient cohort: {resp.matched_patients} patients share this "
        f"profile's conditions; {resp.quoteable} have quoteable treatment reports."
    ]
    for p in resp.predictions:
        parts.append(f"{_fmt_pred(p)} — cohort reports in this class: {p.evidence_count}")
    for cls, quotes in (resp.quotes or {}).items():
        for q in quotes:
            parts.append(
                f"Quote [{cls}] ({q.sentiment}, drug={q.drug}, post_id={q.post_id}): \"{q.text}\""
            )
    return "\n".join(parts) + f"\n\nDisclaimer: {resp.disclaimer}"


@tool(["DashboardChatbot"])
def get_quote_context(post_id: str) -> str:
    """Fetch the full post (title + body) behind a quote's post_id, for context."""
    post = _SVC.get_post_detail(post_id)
    if post is None:
        return f"No post was found for post_id={post_id} (it may not exist in this dataset)."
    body = (post.body_text or "").strip()
    body = body[:1200] + ("…" if len(body) > 1200 else "")
    return (
        f"Post {post.post_id} (user {post.user_id}, flair: {post.flair}):\n"
        f"Title: {post.title or '(none)'}\n"
        f"Body: {body or '(empty)'}"
    )


@tool(["DashboardChatbot"])
def get_comorbidity(conditions: list[str], severity: str) -> str:
    """Conditions enriched (by lift) among patients who share this profile — co-occurrence, not diagnosis."""  # noqa: E501
    resp = _SVC.comorbidity(list(conditions), severity or None)
    if resp is None:
        return "Co-occurrence patterns are unavailable right now (could not read the dataset)."
    if resp.cohort_size == 0 or not resp.patterns:
        return _NO_COHORT
    lines = [
        f"{pat.condition}: {pat.cohort_count} of {resp.cohort_size} cohort patients "
        f"({pat.cohort_pct}% vs {pat.baseline_pct}% population, lift {pat.lift}x)"
        for pat in resp.patterns
    ]
    return (
        f"Cohort of {resp.cohort_size} patients (population {resp.population}). "
        "Conditions over-represented among patients like this:\n- "
        + "\n- ".join(lines)
        + f"\n\nDisclaimer: {resp.disclaimer}"
    )


@tool(["DashboardChatbot"])
def lit_search(query: str) -> str:
    """Search the scientific literature (PubMed/Europe PMC/OpenAlex) and summarize the evidence for a query."""  # noqa: E501
    resp = _SVC.lit_search(query)
    if resp.error and not resp.articles:
        return f"Literature search for \"{query}\": {resp.error}"
    parts = [f"Literature for \"{query}\":"]
    if resp.llm_summary:
        parts.append(resp.llm_summary.strip())
    for a in (resp.articles or [])[:6]:
        meta = " · ".join(
            x for x in [a.evidence_type, a.journal, str(a.year) if a.year else None, a.signal] if x
        )
        parts.append(f"[{a.citation_id}] {a.title} ({meta}) {a.url}")
    if resp.disclaimer:
        parts.append(f"Disclaimer: {resp.disclaimer}")
    return "\n".join(parts)


@tool(["DashboardChatbot"])
def get_explain(category: str, conditions: list[str], severity: str) -> str:
    """Plain-language, non-prescriptive explanation of why a drug class might or might not help this profile."""  # noqa: E501
    resp = _SVC.explain(category, list(conditions), severity or None)
    return f"{resp.text}\n(explanation source: {resp.source})"


@tool(["DashboardChatbot"])
def acknowledge_missing_data(topic: str) -> str:
    """Record that the dashboard has no data for a topic so the answer can say so honestly."""
    return (
        f"The dashboard does not have data to answer '{topic}'. Tell the user plainly that this "
        "information is not available in the dataset rather than guessing — for cohort/'patients "
        "like me' questions the conditions table is sparse, so there may be no cohort to draw on."
    )
