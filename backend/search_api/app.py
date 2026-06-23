from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from backend.search_api.models import (
    ChatRequest,
    ChatResponse,
    ComorbidityResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
    MetadataResponse,
    PostDetailResponse,
    ExplainRequest,
    ExplainResponse,
    LitSearchRequest,
    LitSearchResponse,
    PredictRequest,
    PredictResponse,
    TreatmentEvidenceResponse,
    UserPostsRequest,
    UserPostsResponse,
)
from backend.search_api.comorbidity import comorbidity as comorbidity_patterns
from backend.search_api.evidence import explain as explain_treatment
from backend.search_api.evidence import treatment_evidence
from backend.search_api.litsearch import lit_search
from backend.search_api.predict import predict as predict_treatments
from backend.search_api.service import get_metadata, get_post_detail, get_user_posts, keyword_search
from backend.shared_db import BASE_DIR, DB_PATH


FRONTEND_DIR = BASE_DIR.parent / "frontend"
WEIGHTED_PAGE = FRONTEND_DIR / "weighted_keyword_explorer.html"
PROTOTYPE_PAGE = FRONTEND_DIR / "subtype_explorer_prototype.html"
PREDICT_PAGE = FRONTEND_DIR / "treatment_predictor.html"
LITSEARCH_JS = FRONTEND_DIR / "litsearch.js"
CHAT_JS = FRONTEND_DIR / "chat.js"

app = FastAPI(
    title="PatientPunk Weighted Search API",
    version="0.1.0",
    description="Server-backed weighted keyword search over the PatientPunk SQLite corpus.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,   # wildcard origin + credentials is an invalid combo (browsers reject)
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse(url="/weighted_keyword_explorer.html")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "database": DB_PATH.name}


@app.get("/api/metadata", response_model=MetadataResponse)
def api_metadata() -> MetadataResponse:
    return get_metadata()


@app.post("/api/keyword-search", response_model=KeywordSearchResponse)
def api_keyword_search(request: KeywordSearchRequest) -> KeywordSearchResponse:
    return keyword_search(request)


@app.post("/api/user-posts", response_model=UserPostsResponse)
def api_user_posts(request: UserPostsRequest) -> UserPostsResponse:
    return get_user_posts(request.user_id, request.terms, post_limit=request.post_limit)


@app.post("/api/predict", response_model=PredictResponse)
def api_predict(request: PredictRequest) -> PredictResponse:
    """Predict each drug-class's chance of a positive experience for a patient's tracked variables."""
    return predict_treatments(request)


@app.post("/api/treatment-evidence", response_model=TreatmentEvidenceResponse)
def api_treatment_evidence(request: PredictRequest) -> TreatmentEvidenceResponse:
    """Predictions + a real similar-patient cohort (shared conditions) + quoteable evidence per class."""
    return treatment_evidence(request)


@app.post("/api/comorbidity", response_model=ComorbidityResponse)
def api_comorbidity(request: PredictRequest) -> ComorbidityResponse:
    """Diagnosis Evidence: conditions enriched (by lift) among patients sharing this profile."""
    return comorbidity_patterns(request)


@app.post("/api/lit-search", response_model=LitSearchResponse)
def api_lit_search(request: LitSearchRequest) -> LitSearchResponse:
    """Free-text literature search + deterministic evidence summary (PubMed/Europe PMC/OpenAlex)."""
    return lit_search(request)


@app.post("/api/explain", response_model=ExplainResponse)
def api_explain(request: ExplainRequest) -> ExplainResponse:
    """Real-time LLM explanation of why a treatment class might help this profile (falls back if no key)."""
    return explain_treatment(request)


@app.post("/api/chat", response_model=ChatResponse)
def api_chat(request: ChatRequest) -> ChatResponse:
    """Data-grounded chatbot turn: Rumi tool-loop answer → runtime SafetyFilter gate.

    Never 500s — any LLM/network/import failure degrades to a graceful 200 fallback
    so the widget always gets a usable reply. The server is stateless; multi-turn
    memory comes from Rumi keyed on the client-supplied conversation_id.
    """
    # Imported lazily so the rest of the API (and its tests) never pays the Rumi
    # import cost, and a missing OPENROUTER_API_KEY can't break unrelated routes.
    from agentic_health_hackathon.chatbot.runtime import answer
    from agentic_health_hackathon.shared_decision.safety import SafetyFilter

    profile = {"conditions": list(request.profile.conditions), "severity": request.profile.severity}
    try:
        result = answer(
            request.message,
            request.conversation_id,
            profile,
            request.current_predictions,
        )
        gated = SafetyFilter().apply(result["raw_text"], had_tool_calls=result["had_tool_calls"])
        return ChatResponse(
            assistant_message=gated.text,
            sources=result.get("sources", []),
            disclaimers=gated.disclaimers,
            blocked=gated.blocked,
            conversation_id=request.conversation_id,
        )
    except Exception:
        # Graceful fallback — still carry the safety disclaimer.
        fallback = SafetyFilter().apply(
            "I'm having trouble reaching the data right now. Please try again in a moment — "
            "and remember I only show what patients reported, for discussion with your doctor.",
            had_tool_calls=False,
        )
        return ChatResponse(
            assistant_message=fallback.text,
            sources=[],
            disclaimers=fallback.disclaimers,
            blocked=False,
            conversation_id=request.conversation_id,
        )


@app.get("/api/post/{post_id}", response_model=PostDetailResponse)
def api_post_detail(post_id: str) -> PostDetailResponse:
    post = get_post_detail(post_id)
    if post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return post


@app.get("/weighted_keyword_explorer.html", include_in_schema=False)
def weighted_keyword_explorer() -> FileResponse:
    return FileResponse(WEIGHTED_PAGE)


@app.get("/subtype_explorer_prototype.html", include_in_schema=False)
def subtype_explorer_prototype() -> FileResponse:
    return FileResponse(PROTOTYPE_PAGE)


@app.get("/treatment_predictor.html", include_in_schema=False)
def treatment_predictor() -> FileResponse:
    return FileResponse(PREDICT_PAGE)


@app.get("/litsearch.js", include_in_schema=False)
def litsearch_js() -> FileResponse:
    return FileResponse(LITSEARCH_JS, media_type="application/javascript")


@app.get("/chat.js", include_in_schema=False)
def chat_js() -> FileResponse:
    return FileResponse(CHAT_JS, media_type="application/javascript")
