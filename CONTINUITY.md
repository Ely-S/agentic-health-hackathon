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
- [ ] **Similarity method** — which fields, what encoding (presence vs value-level), what
  distance? **Heads-up landmine:** at the dataset level, the "obvious" patient clustering is
  partly a **verbosity artifact** — patients who write more look more similar (more fields
  filled), independent of phenotype. Control for this (e.g. restrict to patients with ≥N
  fields, or normalize) or your "similar patients" will just be "wordy patients."
- [ ] **Treatment ranking** — weight by patient similarity? How to handle the
  positive-reporting bias and small-n drugs (366 drugs have ≥5 reports; many have 1–2)?
- [ ] **Normalization** — condition/drug free-text is high-cardinality (e.g. mcas vs "mast
  cell activation"); a controlled vocab sharpens both similarity and the viz.
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
