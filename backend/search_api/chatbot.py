"""ChatbotQueryService — one typed facade over the 8 existing in-process query fns.

The Rumi chatbot tools (and any future route) call THIS, never the underlying
functions directly, so there is a single validated path: the request models are
built here, sqlite errors are caught and turned into an honest "data unavailable"
result, and the empty-cohort case is flagged explicitly. No new SQL lives here —
this is pure delegation to:

    predict            (predict.py:50)
    treatment_evidence (evidence.py:142)
    explain            (evidence.py:231)
    comorbidity        (comorbidity.py:88)
    lit_search         (litsearch.py:47)
    keyword_search     (service.py:564)
    get_post_detail    (service.py:592)
    get_user_posts     (service.py:622)
"""

from __future__ import annotations

import sqlite3

from backend.search_api.comorbidity import comorbidity as _comorbidity
from backend.search_api.evidence import explain as _explain
from backend.search_api.evidence import treatment_evidence as _treatment_evidence
from backend.search_api.litsearch import lit_search as _lit_search
from backend.search_api.predict import predict as _predict
from backend.search_api.service import get_post_detail as _get_post_detail
from backend.search_api.service import get_user_posts as _get_user_posts
from backend.search_api.service import keyword_search as _keyword_search
from backend.search_api.models import (
    ComorbidityResponse,
    ExplainRequest,
    ExplainResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
    LitSearchRequest,
    LitSearchResponse,
    PostDetailResponse,
    PredictRequest,
    PredictResponse,
    TreatmentEvidenceResponse,
    UserPostsResponse,
    WeightedTerm,
)


class ChatbotQueryService:
    """Typed delegation layer the chatbot tools call. No new SQL; honest on failure."""

    # ---- pure prediction (no DB read) ----

    def predict(self, conditions: list[str], severity: str | None) -> PredictResponse:
        return _predict(PredictRequest(conditions=list(conditions), severity=severity))

    # ---- cohort-backed evidence (DB read; may be empty) ----

    def treatment_evidence(
        self, conditions: list[str], severity: str | None
    ) -> TreatmentEvidenceResponse | None:
        """Predictions + a real similar-patient cohort. ``None`` on a sqlite error.

        A successful result with ``matched_patients == 0`` is the honest
        empty-cohort case (the conditions table is sparse in this dataset) — the
        caller surfaces "no cohort" rather than fabricating one.
        """
        try:
            return _treatment_evidence(
                PredictRequest(conditions=list(conditions), severity=severity)
            )
        except sqlite3.Error:
            return None

    def comorbidity(
        self, conditions: list[str], severity: str | None
    ) -> ComorbidityResponse | None:
        try:
            return _comorbidity(PredictRequest(conditions=list(conditions), severity=severity))
        except sqlite3.Error:
            return None

    # ---- explanation (LLM with deterministic fallback; no key needed) ----

    def explain(
        self, category: str, conditions: list[str], severity: str | None
    ) -> ExplainResponse:
        return _explain(
            ExplainRequest(category=category, conditions=list(conditions), severity=severity)
        )

    # ---- literature (network; degrades to error field, never raises) ----

    def lit_search(self, query: str, max_results: int = 8) -> LitSearchResponse:
        return _lit_search(LitSearchRequest(query=query, max_results=max_results))

    # ---- post + cohort lookups (DB read) ----

    def get_post_detail(self, post_id: str) -> PostDetailResponse | None:
        try:
            return _get_post_detail(post_id)
        except sqlite3.Error:
            return None

    def keyword_search(self, request: KeywordSearchRequest) -> KeywordSearchResponse | None:
        try:
            return _keyword_search(request)
        except sqlite3.Error:
            return None

    def get_user_posts(
        self, user_id: str, terms: list[WeightedTerm], *, post_limit: int = 12
    ) -> UserPostsResponse | None:
        try:
            return _get_user_posts(user_id, terms, post_limit=post_limit)
        except sqlite3.Error:
            return None
