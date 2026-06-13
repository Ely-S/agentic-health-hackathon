# Tracker

## Session Goal

Review `DATA_AND_PRODUCT_ARCHITECTURE.md`, turn its claims into runnable analysis, and translate the strongest findings into a cleaner product direction for a subtype explorer.

## Completed

### 1. Architecture Review

- Reviewed `DATA_AND_PRODUCT_ARCHITECTURE.md` in detail.
- Validated the product thesis against the actual `patientpunk.db` schema and the existing `cluster_explorer` code.
- Cross-checked the architecture assumptions against the real database coverage and helper modules.

### 2. Analysis Notebook

- Created `DATA_AND_PRODUCT_ARCHITECTURE_analysis.ipynb`.
- Added executable analysis for:
  - database overview
  - field coverage / cohort readiness
  - patient quality scoring
  - condition normalization preview
  - condition co-occurrence
  - treatment ranking
  - treatment x condition matrix
  - `POTS only` vs `POTS + MCAS`
  - LDN stratification by severity, trajectory, duration, and onset
  - exploratory clustering
- Smoke-tested the notebook logic end to end.
- Fixed notebook portability issues:
  - added Python 3.9-safe typing behavior
  - added a fallback for `display()`
  - corrected empty-string handling so coverage metrics reflect real populated data
  - overrode the existing cluster preset logic so the “strict core” cohort uses cleaned field presence

### 3. Notebook Runtime Setup

- Started a local Jupyter notebook server for browser exploration.
- Diagnosed a failed `jupyter lab` launch and switched to a working `python3 -m notebook` flow.
- Installed `ipykernel` into `.venv`.
- Registered the project virtual environment as a Jupyter kernel: `Python (.venv)`.
- Updated notebook metadata so it prefers the project kernel instead of the system kernel.

### 4. Rendered Output Review

- Reviewed `explorer.html` after the notebook output was rendered to HTML.
- Extracted the most important findings from the rendered output rather than relying only on notebook code.
- Identified a meaningful issue in the naive condition canonicalization logic:
  - `me_cfs` overmatched because of substring matching on `me`
  - `multiple_sclerosis` overmatched because of substring matching on `ms`
  - `eds` was undercounted / incompletely captured

### 5. Product Specification

- Wrote `SPA_PRODUCT_SPEC.md`.
- Defined a lean single-page product architecture centered on:
  - left-rail intake
  - center evidence pane
  - right-side detail drawer
- Scoped MVP versus non-MVP functionality.
- Documented ranking logic, support tiers, trust requirements, and minimum derived tables needed before launch.

### 6. Frontend Mockup

- Created `subtype_explorer_mockup.html`.
- Designed a cleaner subtype explorer interface with:
  - guided profile intake
  - treatment evidence cards
  - quote evidence drawer
  - subtype comparison panel
- Expanded the intake model to include:
  - symptom selection
  - prior treatment response selection
- Added:
  - target symptom selection
  - treatment response badges on evidence cards

### 7. Diagnosis Exploration Mode

- Added a second top-level product mode for diagnosis-pattern exploration.
- Expanded the diagnosis concept beyond a small preview into a fuller workflow:
  - diagnosis evidence tab
  - diagnosis cards
  - “why this diagnosis appears” evidence view
  - symptom clue checklist
  - clinician discussion prompts
  - diagnosis-focused right drawer

### 8. Interactive Prototype

- Built `subtype_explorer_prototype.html`.
- Added working interaction for:
  - tab switching between treatment and diagnosis modes
  - clickable treatment cards that update the right drawer
  - clickable diagnosis cards that update:
    - the evidence workspace
    - clue checklist
    - clinician prompt panel
    - diagnosis drawer
  - toggleable intake chips for lightweight interactivity
- Opened both the static mockup and the interactive prototype locally for review.

### 9. Server-Backed Weighted Search

- Split the weighted keyword explorer into a standalone page: `weighted_keyword_explorer.html`.
- Confirmed that browser-side SQLite access was the wrong fit for this stage:
  - local file loading was brittle
  - CDN/runtime dependency issues left the UI stuck waiting for DB access
  - shipping large client-side data bundles was not a good long-term path
- Chose a small Python API server over a second frontend/backend stack:
  - selected FastAPI rather than Flask or a Streamlit-only path
  - kept the implementation aligned with the existing Python + SQLite codebase
- Standardized on `patientpunk.db` as the primary search database rather than `posts.db`.
- Added shared database access in `shared_db.py` so both the existing cluster workbench and the new API use the same DB path.
- Updated `cluster_explorer/data.py` to reuse the shared DB helper.
- Created a new API package in `search_api/` with:
  - `search_api/app.py`
  - `search_api/models.py`
  - `search_api/service.py`
- Implemented the first server contract:
  - `GET /health`
  - `GET /api/metadata`
  - `POST /api/keyword-search`
  - `GET /api/post/{post_id}`
- Locked the weighted keyword search request/response shape around:
  - typed weighted terms
  - cohort counts
  - cohort-change history
  - ranked posts
  - top treatment summaries
  - post-detail drilldown
- Rewrote `weighted_keyword_explorer.html` to call the API instead of trying to read SQLite in the browser.
- Added FastAPI runtime dependencies to `requirements.txt`:
  - `fastapi`
  - `uvicorn`
  - `pydantic`
- Installed the new server dependencies into the project `.venv`.
- Smoke-tested:
  - Python module syntax
  - standalone frontend script syntax
  - direct service calls against `patientpunk.db`
  - live HTTP endpoints on the FastAPI server
  - served HTML for the standalone explorer

## Files Created

- `DATA_AND_PRODUCT_ARCHITECTURE_analysis.ipynb`
- `SPA_PRODUCT_SPEC.md`
- `subtype_explorer_mockup.html`
- `subtype_explorer_prototype.html`
- `weighted_keyword_explorer.html`
- `shared_db.py`
- `search_api/__init__.py`
- `search_api/app.py`
- `search_api/models.py`
- `search_api/service.py`
- `TRACKER.md`
- `LEARNINGS.md`

## Files Updated

- `DATA_AND_PRODUCT_ARCHITECTURE_analysis.ipynb`
- `subtype_explorer_mockup.html`
- `subtype_explorer_prototype.html`
- `weighted_keyword_explorer.html`
- `cluster_explorer/data.py`
- `requirements.txt`

## Main Open Issues

- Condition canonicalization is not safe enough for product use yet.
- Diagnosis-mode condition evidence is only as good as the canonical mapping behind it.
- The clustering slice remains exploratory and should not be treated as validated phenotype structure.
- The standalone weighted explorer now has a real API path, but the broader subtype explorer prototype is still mostly static and not yet backed by derived evidence tables.
- Keyword search currently uses weighted `LIKE` matching rather than FTS5, so it is functional but still a V1 retrieval layer.
- Treatment ranking for keyword cohorts still needs a reviewed treatment canonicalization layer to suppress placeholder or low-specificity entities more safely.

## Recommended Next Steps

1. Replace naive substring condition matching with a reviewed canonical mapping table.
2. Recompute diagnosis and condition-level notebook outputs after canonicalization is fixed.
3. Build derived backend tables:
   - `condition_canonical_map`
   - `treatment_canonical_map`
   - `patient_quality_score`
   - `treatment_signal_summary`
4. Upgrade keyword search from weighted `LIKE` matching to SQLite FTS5 behind the same API contract.
5. Extend the FastAPI layer so the main subtype explorer can retrieve:
   - live treatment evidence cohorts
   - quote drawers
   - diagnosis-pattern evidence
6. Convert the rest of the interactive prototype into a real SPA shell backed by those derived tables and API endpoints.
