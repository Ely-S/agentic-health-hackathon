# CONTINUITY — shared notes for agents & contributors

**Purpose.** A living scratchpad for *everyone* working on this hackathon — humans and AI
agents alike. Use it for context handoffs, strategy/decisions, conventions, the demo plan,
and open questions. Unlike code, this file is meant to be **written to often**.

> **AI agents / instances:** read this file first when you start, and **leave notes at the
> end of your session** — what you changed, what you learned, what's next. Future you (and
> the next agent) will thank you. Humans: same — drop a line when you make a decision.

## How to use this file
- **Append, don't overwrite.** Add dated entries to the **Notes log** at the bottom; don't
  delete or rewrite other people's notes.
- **Sign + date** entries: `YYYY-MM-DD — name / agent`.
- Durable decisions and conventions go in the top sections; transient progress goes in the
  log.
- Keep it honest and concise. If you discover a landmine, write it down here.

---

## Orientation (start here)
- **What we're building:** a "patients-like-me → rank the treatments they reported" agentic
  tool, plus cluster / comorbidity / diagnosis visualizations. See `README.md`.
- **The data:** `docs/DATASET.md` (source + structure), `docs/CODEBOOK.md` (fields + stats),
  `docs/PRIVACY.md` (anonymization + risk).
- **Upstream:** the dataset + extraction pipeline come from PatientPunk
  (<https://github.com/Ely-S/PatientPunk>). We build the *app* on top.

## Hard rules / conventions (don't break these)
1. **NO patient data in this repo — ever.** No `.db`, no raw `.json`/`.csv` of patient text
   or per-patient records. Data lives in **controlled S3** (presigned links). The repo holds
   only code, docs, codebooks, and **aggregate** stats. This is enforced in `.gitignore` and
   is a deliberate privacy/hygiene choice (`docs/PRIVACY.md`). If you need data, get a
   presigned link from a maintainer.
2. **Not medical advice.** Frame everything as lived-experience evidence / hypothesis
   generation. This matters to the health judges.
3. **Be honest in claims** — especially the anonymization limits (unsalted hash) and the
   strong "what-helped-me" reporting bias in the treatment data.
4. **Keep judge-facing docs accurate.** If the dataset changes, update the numbers in
   `docs/CODEBOOK.md`.

## Demo outline (DRAFT — modify freely)
Target ~3–5 min live demo for judges. Treat this as a starting skeleton; rework it.

1. **Hook (15s).** "If you have Long COVID, there's no clinical trial waiting for you — but
   thousands of patients have already tried things and written down what happened. What if
   you could instantly find the ones most like you and see what worked?"
2. **Input (30s).** Show the intake: user enters symptoms + diagnosis (free text or
   checkboxes). The agent asks 1–2 clarifying questions to place them (LLM
   disambiguation / segmentation).
3. **Patients like me (45s).** Surface the nearest-neighbor patients; show a couple of their
   (public) posting snippets so it feels grounded and real.
4. **Ranked treatments — the payoff (60s).** Treatments ranked by what worked for *those*
   similar patients, from the 9,831 drug-sentiment reports. e.g. a POTS/MCAS-leaning profile
   surfaces LDN / antihistamines / magnesium / beta blockers; show the positive/negative
   split per treatment.
5. **Visual exploration (45s).** Diagnosis heatmap (symptoms × diagnoses), patient clusters
   (symptoms + treatment response), and overlapping conditions — let judges see the
   population structure.
6. **Trust & limits (20s).** One line: public Reddit source, anonymized, controlled data,
   "lived experience, not medical advice." Builds credibility.
7. **Stretch, if built (20s).** Agent pulls a clinical study and synthesizes it alongside
   the Reddit evidence.
8. **Close (15s).** Impact: turning scattered patient experience into a personalized,
   navigable evidence base.

*Demo safety:* pre-load an example profile in case live input is slow; keep screenshots of
the visualizations in case live rendering breaks.

## Open questions / TODO
- [ ] Clean up the data (owner: Shaun). [ ] Investigate sub-typing (owner: Eli).
- [x] **Verbosity confound — RESOLVED (2026-06-13).** Presence encoding is verbosity-driven
  (PC1↔n_fields_filled r=**+0.95**). Fix: analysis-grade fields → IDF-weight → **L2-normalize
  (cosine)** drops it to r=**+0.02** (leakage η² 0.63→0.03). The **L2/cosine** step is the
  lever (removes vector magnitude = the 1-count = verbosity); IDF alone doesn't. Use
  `data/clean/model_matrix_controlled.csv`; see `scripts/verbosity_control.py` + notes log.
- [ ] **Similarity method** — with verbosity controlled, **hard clustering is weak**: best
  k=2 just splits "explicitly stated long_covid+covid" (n=589) vs the comorbidity-rich rest
  (n=3,777); silhouette ~0.4 but for a *labeling* reason, not phenotype. The conditions overlap
  as a **continuum, not discrete clusters** (the long_covid↔POTS↔MCAS↔dysautonomia↔EDS↔ME/CFS
  web). **Implication: for "patients like me" use nearest-neighbor SIMILARITY on the controlled
  cosine matrix — not hard cluster labels.** Open: distance/k for kNN; whether to soft-cluster
  or LLM-impute (yes/no/unknown) to sharpen subtypes.
- [ ] **Treatment ranking** — weight by patient similarity? How to handle the
  positive-reporting bias and small-n drugs (366 drugs have ≥5 reports; many have 1–2)?
- [ ] **Normalization** — condition/drug free-text is high-cardinality (e.g. mcas vs "mast
  cell activation"); a controlled vocab sharpens both similarity and the viz.
- [ ] **DATA QUALITY (BLOCKER) — DeepSeek over-calls POSITIVE** (asymmetric; ~10–20% false
  positives; negatives reliable). The ~78–80% positive rate is partly artifact. Audit to pin the
  rate + check if uniform vs differential; consider re-running sentiment with a neutral/no-effect
  class. **Trust contraindication signals over soft positives.** See notes log 2026-06-13.
- [x] **Treatment-effect heterogeneity + per-drug efficacy logits — DONE (branch `clustering_analysis`).**
  Continuum, not clusters → model drug-class × syndrome. Headline: neuro-psych worse for EDS;
  antihistamine→MCAS & LDN→fibromyalgia better. Scoring artifact:
  `data/clean/drug_logit_coefficients.csv`. See notes log.
- [ ] Clinical-study retrieval + synthesis (stretch).

## Notes log (append below — newest at the bottom)
- **2026-06-13 — Claude (Opus 4.8, working with Shaun).** Created the repo docs: `README.md`,
  `docs/DATASET.md`, `docs/PRIVACY.md`, `docs/CODEBOOK.md`, `docs/field_dictionary.csv`, and
  this file. Established the **no-data-in-repo** rule (data in controlled S3; codebooks +
  aggregate stats only in git). Dataset = a 2-month r/covidlonghaulers slice: **4,366
  patients, 95 variables, 9,831 drug-sentiment reports** (the treatment signal). Biggest
  thing to know building the app: the per-patient clustering signal is confounded by
  posting verbosity (see Open Questions) — and the condition free-text needs normalization
  before similarity/clustering will be clean. Drug-sentiment is the strongest, cleanest part
  of the dataset (LDN/antihistamines/magnesium/etc. with pos/neg splits). Next agent: pick
  up the similarity layer; mind the verbosity confound.
- **2026-06-13 — Claude (Opus, w/ Shaun), re: Eli's agent flag on condition canonicalization.**
  Eli's agent flagged that `me_cfs` / `multiple_sclerosis` / `eds` results might be invalid
  (substring "me" over-matching, words-ending-"ms" over-matching, eds undercounted). **Audited
  against the real data:**
  - **`me_cfs` — no false positives.** Only `me/cfs` (390) + `chronic fatigue` (4) map to it.
    The substring "me" is *not* matched.
  - **`ms` — no false positives.** Only the literal `ms` (55) maps; nothing ending in "ms".
  - **`eds` — canonicalization is fine** (captures all ~85 EDS-looking values in the
    `conditions` field, none missed) — **but eds IS undercounted for a *different* reason:
    the signal is split across fields.** 63 patients carry EDS/hypermobility in
    `connective_tissue_symptoms` (`cci`, `hypermobility`, `heds`, `ehlers danlos`…), and **33
    of them never appear in `conditions`.** True EDS ≈ **119** (conditions ∪ connective_tissue)
    vs **86** from `conditions` alone (~28% low).

  **Why the substring risk doesn't bite our code:** the modeling mapper
  (`scripts/clean_encode.py`) uses **exact match** (no substring at all); the exploratory
  heatmap mapper (PatientPunk `normalize.py`) uses **guarded** substring — surface forms must
  be **length ≥ 4 with word boundaries**, so 2-letter tokens ("me","ms") can only match
  exactly, never as substrings. Eli's instinct (short-token substring matching is a footgun)
  is the right general rule — it just isn't present here.

  **TODO for condition-level prevalence/clustering:** aggregate split conditions across related
  fields (EDS ← `conditions` + `connective_tissue_symptoms`; likely also MCAS, dysautonomia,
  SFN). The codebook's per-field counts (EDS 81) are correct *for the conditions field* but
  understate true prevalence — account for this when the app computes condition prevalence.
- **2026-06-13 — Claude (Opus, w/ Shaun): verbosity confound CONTROLLED + hard-clustering finding.**
  Built `scripts/clean_encode.py` (multi-hot encode all 95 fields → `data/clean/model_matrix.csv`,
  4,366×1,374, + `column_manifest.csv`) and `scripts/verbosity_control.py`.
  **Verbosity:** presence encoding PC1↔n_fields_filled r=**+0.95** (clusters = verbose vs terse).
  Controlled rep = analysis-grade fields → IDF → **L2/cosine** → r=**+0.02**, leakage η² 0.63→0.03.
  The L2/cosine normalization is the lever (removes vector magnitude = the 1-count = verbosity);
  IDF alone insufficient. Output: `data/clean/model_matrix_controlled.csv` (4,366×289, cosine-ready;
  carries `n_fields_filled`, `n_values`, `eds_any`).
  **Hard-clustering finding (important for the app):** with verbosity gone, k-means is weak — best
  k=2 is a trivial "stated long_covid+covid (n=589)" vs "comorbidity-rich rest (n=3,777)" split;
  silhouette ~0.4 but for a labeling reason, not phenotype. Conditions are a **continuum, not
  clusters** → **for "patients like me" use kNN similarity on the controlled matrix, NOT hard
  clusters.** Next: validate kNN (seed phenotypes → neighbors share phenotype), consider
  soft/overlapping clustering or LLM yes/no/unknown imputation to sharpen subtypes.
  **Conditions (Eli's flag):** me_cfs/ms canonicalization clean (no false positives); EDS
  undercounted in `conditions` alone (86) → use `eds_any` (119, cross-field) — now a column in the
  controlled matrix. **Data:** cleaned matrices + reports + the DB bundled to controlled S3
  `s3://patientpunk/6_11_hackathon/` for Eli (ask a maintainer for a presigned link).
- **2026-06-13 — Claude (Opus, w/ Shaun): treatment-effect heterogeneity + drug-efficacy logits + a SENTIMENT DATA-QUALITY problem. (CURRENT STATE / handoff.)**
  All of this is on branch **`clustering_analysis`** (scripts committed; data outputs in gitignored
  `data/clean/`; nothing merged to `main`).

  **Where the clustering arc landed:** there are NO clean patient clusters — the spectrum is a
  **continuum**. The actionable structure is not patient clusters but **drug-class × syndrome
  interactions** (which treatments work/fail for which part of the spectrum).

  **kNN similarity** (`scripts/knn_sanity.py`): controlled cosine space gives phenotype-coherent
  neighbors. Correction to an earlier claim: plain **presence+cosine matches phenotype as well as /
  better than the IDF-weighted** version (IDF down-weights the marker conditions); residual
  neighbor-verbosity corr is mostly legitimate (verbosity ≈ comorbidity burden). App: cosine kNN on
  dense fields, skip IDF.

  **Treatment heterogeneity** (`treatment_heterogeneity.py`, `treatment_spectrum_models.py`,
  `treatment_pooled_model.py`, `treatment_logit_predictive.py`):
  - **Robust signals (survive pooling + FDR):** neuro-psychiatric (SSRI-type) drugs WORSE for
    **EDS** (OR ~0.25–0.31; ~33% positive vs ~73% baseline — strongest, most reproducible finding);
    autonomic/CV worse for MCAS (OR 0.44); supplement/mito worse for ME/CFS; antiviral/anticoag
    worse for MCAS. **Better:** antihistamines for MCAS/housebound (adj OR ~2–4); **LDN for
    fibromyalgia** (OR ~3.5, matches real off-label use); metabolic (metformin/GLP-1) for
    fibromyalgia/SFN. Autonomic/CV broadly well-tolerated.
  - **Pooled partially-pooled model** = the recommended vehicle: one L2 logistic over all reports,
    `P(positive) ~ drug_group*condition`, patient-bootstrap CIs, broad mechanism drug groups for power.
  - **Per-drug PREDICTIVE logits** → **`data/clean/drug_logit_coefficients.csv`** = a scoring
    artifact (`logit = const + Σ coef·predictor`) for "given a patient's conditions, P(success) for
    drug X." Widened groups cover 52% of reports.
  - Cleaning: `symptom_trajectory` regex-normalized to 5 buckets in `clean_encode.py` (was 28 junk
    values); matrices regenerated; verbosity control unchanged.

  **⚠️ NEW PROBLEM — DeepSeek over-calls POSITIVE (sentiment data quality).** Audited labels vs
  source text. Error is **asymmetric**: negatives reliable (6/6 read correct); positives
  contaminated. Real mislabels found as `positive`: *"didn't move the needle either way"* (no
  effect), *"[it] stopped working"* (past-positive-now-failed), *"just started last week, showing
  promise"* (aspirational), a drug merely listed among 4 prescribed. Explicit-error-phrase floor =
  3.4% of positives; manual read of 9 random positives → ~2 clear errors (~22%); true
  false-positive rate likely **~10–20%**, NOT yet pinned. **Root cause:** schema has no
  *neutral/no-effect* class, so neutral/early/recommendation mentions round up to positive (+ LLM
  positivity lean). **Consequence:** the ~78–80% positive rate is partly artifact → **trust the
  negative/contraindication signals, distrust the soft positives** (our headline findings ARE
  negatives, so they hold; "success" signals are shakier). Relative comparisons hold *only if* the
  over-call rate is uniform across drugs/conditions — **UNVERIFIED**.

  **NEXT STEPS (in order):**
  1. **Labeled sentiment audit (~100 reads)** → pin the false-positive rate AND test whether it's
     uniform or differs by drug/condition (differential = biases the heterogeneity models).
  2. If material/differential: **re-run DeepSeek sentiment with a corrected prompt** (add
     neutral/no-effect class; ignore aspirational/just-started; require an attributed outcome).
  3. **Finalize predictive logits conditions+severity only** — DROP `symptom_trajectory` as a
     predictor (outcome-adjacent → "improving" → spurious "success" via reverse causation); wrap
     `drug_logit_coefficients.csv` in a `predict_drug_success(conditions)` helper.
  4. Optional: soft/overlapping clustering (NMF/archetypes) for "syndrome axes"; widen drug groups
     further; multivariable disentangling of overlapping conditions.
