# Agentic Health Hackathon — "Patients Like Me"

An agentic tool that takes a patient's symptoms, background, and diagnosis, finds
**real patients who are similar to them**, and **ranks the treatments those patients
reported** — surfacing lived-experience evidence from a large corpus of
patient-authored Reddit data, with cluster and comorbidity visualizations on top.

> **For judges:** this README and the `docs/` folder explain *the dataset we build on*,
> *how it was collected*, *what is new in this hackathon vs. prior work*, and *how the
> data is anonymized and why we believe it adds negligible risk beyond what is already
> public*. Start with [`docs/DATASET.md`](docs/DATASET.md) and [`docs/PRIVACY.md`](docs/PRIVACY.md).

---

## What we are building (this hackathon)

A "find patients like me → see what worked for them" experience:

1. **Input** — the user enters symptoms, background, and diagnosis (free text or a
   checkbox form).
2. **Disambiguate / segment** — an LLM conversation clarifies the input and asks the
   questions needed to place the user within the patient population.
3. **Nearest-neighbor patients** — we retrieve the most similar patients from the
   dataset and surface their (public) posting history.
4. **Treatment ranking** — we rank treatments by what worked for those nearest-neighbor
   patients, using the per-(patient, drug) sentiment already extracted in the dataset.
5. **Visual exploration** — a symptom × diagnosis "diagnosis heatmap", a visual
   exploration of patient clusters (symptoms + treatment response), and overlapping
   conditions.
6. **Stretch** — the agent retrieves clinical studies and synthesizes them alongside the
   Reddit evidence.

This is **decision-support / hypothesis-generation from lived experience, not medical
advice.** The underlying signal is what patients *said* helped them, not clinical trials.

---

## New here vs. built on prior work

To be explicit for judging — what this hackathon contributes vs. what it stands on:

| | Prior work — **PatientPunk** (the foundation) | **This hackathon** |
|---|---|---|
| Data collection (r/covidlonghaulers via the public Reddit archive) | ✓ | — |
| Extraction pipeline → `patientpunk.db` (per-patient variables, per-drug sentiment, demographics) | ✓ | — |
| The agentic app (intake → similar patients → ranked treatments) | — | ✓ *(in progress)* |
| Patient similarity / clustering | — | ✓ — **in development; no finalized algorithm yet** |
| Exploratory analysis (comorbidity structure, data cleaning/encoding, codebook, cluster-readiness) | — | ✓ |
| Visualizations (diagnosis heatmap, clusters, overlapping conditions) | — | ✓ |

The **dataset and the pipeline that produced it** are prior **PatientPunk** work
(<https://github.com/Ely-S/PatientPunk>) — that's the foundation we build on. **Everything we
do *with* the data for this hackathon** — the patient-similarity / clustering approach, the
exploratory comorbidity and cluster analysis, the data cleaning / encoding, and the app — is
created **here**. The clustering/similarity layer is still being developed: **we do not yet
have a finalized algorithm**, and the exploratory analyses were produced at this hackathon.

---

## The dataset at a glance

A 2-month slice of r/covidlonghaulers, structured per patient. Full details in
[`docs/DATASET.md`](docs/DATASET.md); field-by-field codebook in
[`docs/CODEBOOK.md`](docs/CODEBOOK.md).

- **4,366 patients** (distinct post/comment authors), **95 extracted variables**,
  **39,707** structured values.
- **9,831 drug-sentiment reports** across **3,980** drugs — *the treatment-ranking signal*
  (each = a patient reporting a drug helped / hurt / was mixed).
- Built from **2,164 posts + 33,312 comments**, all originally **public** on Reddit.
- Conditions, treatments, symptoms, functional status, and (sparse, self-reported)
  demographics.

---

## How the data was gathered

All extraction ran on **DeepSeek-V3.2 (open-weights) via OpenRouter at temperature 0** —
chosen over frontier models after a head-to-head on this exact task showed it **matched their
coverage of the nuanced, inferential fields at ~1/13 the cost** (and faster, full precision),
so the whole corpus is cheap and reproducible to (re)process. Key decisions:

- **Patient = author, extracted once** — each author's posts *and* comments are merged into
  one document and extracted once per patient (not per post); comments are attributed to their
  *own* author, so commenters are patients too.
- **Regex first, LLM for the gaps**, across a **~95-field "promoted" schema** — a curated base
  set plus fields *discovered inductively* in an earlier pass and promoted to first-class.
- **Drug sentiment in three stages** — extract drug mentions → canonicalize synonyms
  ("low dose naltrexone" → LDN) → classify each *(post, drug)* pair's sentiment. This is the
  treatment-ranking signal.

Full detail and the quality caveats are in [`docs/DATASET.md`](docs/DATASET.md).

---

## Data access — and why no data is in this repo

**No patient data, raw text, or databases live in this repository.** That is a
deliberate design choice for **data hygiene and privacy**:

- The repo contains **only** code, documentation, **codebooks**, **data dictionaries**,
  and **summary statistics** — i.e. *descriptions of* the data, never the data itself.
- The actual dataset (`patientpunk.db`, source corpora, intermediate `.json`/`.csv`)
  lives in **controlled S3 storage** and is shared via **time-limited presigned links or
  on request** — not committed to a public repo, where it would be permanent (git
  history) and world-readable.

This keeps the per-patient data out of public, crawlable, permanent surfaces while still
letting judges and collaborators inspect exactly what the data is (via the codebook and
summary stats here) and obtain it through a controlled channel.

> Need the dataset for evaluation? Request a presigned link — see
> [`docs/DATASET.md`](docs/DATASET.md#getting-the-data).

---

## Privacy in one line

The source posts are **already public** on Reddit; usernames are replaced with hashes;
we create **no new identifying information**; and we keep the assembled data under
controlled access. Full reasoning and the honest limits of the hashing in
[`docs/PRIVACY.md`](docs/PRIVACY.md).

---

## Repository layout

```
README.md                    – this file
docs/
  DATASET.md                 – the data: source, collection, structure, controlled access
  PRIVACY.md                 – anonymization + re-identification risk analysis
  CODEBOOK.md                – 95-field data dictionary, DB schema, summary statistics
  field_dictionary.csv       – the codebook as data (field metadata; not patient data)
```

(Application code is added by hackathon participants; data hygiene rules are enforced in
`.gitignore`.)

---

## Disclaimers

- **Not medical advice.** This is research / hypothesis generation from self-reported,
  unverified patient experience.
- The data is **observational and noisy** — self-reported, with a strong "what helped me"
  reporting bias, and extracted by LLMs (a small fraction of records fall back to
  rule-based extraction). It is suitable for similarity/exploration, **not** for clinical
  efficacy claims.
