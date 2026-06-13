from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse

from backend.search_api.models import (
    ComorbidityResponse,
    KeywordSearchRequest,
    KeywordSearchResponse,
    MetadataResponse,
    PostDetailResponse,
    ExplainRequest,
    ExplainResponse,
    PredictRequest,
    PredictResponse,
    TreatmentEvidenceResponse,
    UserPostsRequest,
    UserPostsResponse,
)
from backend.search_api.comorbidity import comorbidity as comorbidity_patterns
from backend.search_api.evidence import explain as explain_treatment
from backend.search_api.evidence import treatment_evidence
from backend.search_api.predict import predict as predict_treatments
from backend.search_api.service import get_metadata, get_post_detail, get_user_posts, keyword_search
from backend.shared_db import BASE_DIR, DB_PATH


FRONTEND_DIR = BASE_DIR.parent / "frontend"
WEIGHTED_PAGE = FRONTEND_DIR / "weighted_keyword_explorer.html"
PROTOTYPE_PAGE = FRONTEND_DIR / "subtype_explorer_prototype.html"
PREDICT_PAGE = FRONTEND_DIR / "treatment_predictor.html"

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


@app.post("/api/explain", response_model=ExplainResponse)
def api_explain(request: ExplainRequest) -> ExplainResponse:
    """Real-time LLM explanation of why a treatment class might help this profile (falls back if no key)."""
    return explain_treatment(request)


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
