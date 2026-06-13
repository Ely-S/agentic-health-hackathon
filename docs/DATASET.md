# The Dataset

This hackathon builds on the **PatientPunk** dataset: structured, per-patient data
extracted from patient-authored Reddit posts. This document explains where the data
comes from, how it was collected and processed, what it contains, and how to obtain it.

- **Upstream project:** PatientPunk — <https://github.com/Ely-S/PatientPunk>
- **This dataset:** a 2-month slice of r/covidlonghaulers (most recent 60 days of a
  6-month corpus), structured into one record per patient.

---

## Where the data comes from

- **Source:** public posts and comments from **r/covidlonghaulers**, a community of people
  with Long COVID. (The broader PatientPunk project covers additional patient subreddits.)
- **Acquisition:** historical Reddit submissions and comments were obtained via the
  **Arctic Shift** public Reddit archive — i.e. content that was **already publicly posted**
  on Reddit and is publicly archived. No private messages, no scraping behind logins, no
  non-public content.
- **Scope of this slice:** the most recent **60 days** of the corpus —
  **2,164 posts + 33,312 comments**, authored by **4,366 distinct users**.

## How it was processed (raw text → structured data)

The PatientPunk pipeline turns free-text posts into a structured, per-patient database.

**Model.** Every language-model step ran on **DeepSeek-V3.2 (an open-weights model) via
OpenRouter, at temperature 0** (deterministic). DeepSeek was chosen after a measured
head-to-head against frontier models (Claude and others) on this exact extraction task: it
**matched their coverage of the nuanced, inferential fields at ~1/13 the cost**, ran faster,
and at full precision — so the entire corpus can be processed cheaply and reproducibly, with
no frontier-only model required to extend it.

The steps:

1. **Pseudonymize** — every Reddit username is replaced by a SHA-256 hash (`author_hash`)
   at ingest; usernames are not retained downstream. (See [PRIVACY.md](PRIVACY.md) for the
   honest limits of this.)
2. **Per-patient aggregation** — a "patient" = one author. All of that author's posts and
   comments are merged into a single document so we extract **once per patient**, not once
   per post. Comments are attributed to *their own* author, so commenters are patients too.
3. **Variable extraction** — a hybrid of rule-based (regex) extraction and LLM gap-filling
   populates ~95 biomedical fields per patient (conditions, medications, symptoms,
   treatment outcomes, functional status, demographics, …). See [CODEBOOK.md](CODEBOOK.md).
4. **Drug-sentiment extraction** — a separate pipeline finds drug mentions, canonicalizes
   synonyms (e.g. "low dose naltrexone" → "LDN"), and classifies the **sentiment of each
   (post, drug) pair** (positive / negative / mixed). This is the treatment-ranking signal.
5. **Demographics** — a deductive LLM pass extracts self-stated age / sex / location where
   present (these are sparse — most users don't state them).
6. **Assembly** — everything is fused into one SQLite database (`patientpunk.db`).

### Key decisions (and why)

- **Patient = author, extracted once.** We merge each author's posts *and* comments into one
  document and extract once per patient (not per post) — this matches the analysis unit (a
  patient), cuts LLM cost several-fold, and gives the model the patient's full context.
- **Regex first, LLM for the gaps.** Phase 1 uses deterministic regex for well-structured
  patterns (free, reliable); Phase 2 calls the LLM only to fill the *empty* fields across the
  ~95-field schema — cheap where rules suffice, the model only where judgment is needed.
- **A "promoted" schema.** The ~95 fields are a curated base set **plus fields discovered
  inductively** in an earlier pass and promoted to first-class — so the data captures both
  designed and emergent variables.
- **Drug sentiment in three stages.** (1) extract drug mentions per post; (2) canonicalize
  synonyms across all mentions ("low dose naltrexone" → "ldn"); (3) a cheap prefilter ("does
  this post express a personal experience with the drug?") gates a sentiment classifier
  (positive / negative / mixed) on each surviving *(post, drug)* pair.
- **A 2-month slice.** We use the most recent 60 days of a larger 6-month corpus as a
  tractable, current sample.

> Quality note: this is **observational, self-reported** data extracted by automated
> tools. ~1–2% of records fall back to rule-based extraction on parse failures, and a
> handful of the 95 fields are noisy (flagged in the codebook). It is built for
> similarity, exploration, and hypothesis generation — **not** clinical-grade efficacy.

---

## What the data contains

One consolidated SQLite database, `patientpunk.db`, with the following tables:

| table | grain | rows | contents |
|---|---|---|---|
| `unified` | one row per **patient** | 4,366 | wide table: all variables + demographics + drug rollups — *start here* |
| `variables` | patient × field | 39,707 | long/EAV form of every extracted field+value |
| `treatment_reports` | patient × drug mention | 9,831 | **drug → sentiment** (positive/negative/mixed) — the treatment-ranking signal |
| `treatment` | drug | 3,980 | canonical drug names (synonyms grouped) |
| `conditions` | patient × condition | 5,202 | reported illnesses / comorbidities |
| `user_profiles` | patient | 4,366 | demographics (sparse) |
| `posts` | post/comment | 34,948 | the source text (per [PRIVACY.md](PRIVACY.md), this is the already-public Reddit content) |
| `users` | patient | 4,368 | hashed author ids |

**Patient key:** `author_hash` (SHA-256 of the original Reddit username) joins every table.

Headline numbers: **4,366 patients**, **95 variables** (avg ~10.7 populated per patient),
**9,831 drug-sentiment reports** over **3,980 drugs** (366 with ≥5 reports). Full counts,
the field list, and summary statistics are in [CODEBOOK.md](CODEBOOK.md).

---

## Why the data is not in this repository (design choice)

Raw and per-patient data — `patientpunk.db`, the source `posts.db`, and any intermediate
`.json`/`.csv` — is **never committed to this repo.** Public repos are permanent (git
history) and crawlable, which is the wrong surface for assembled health-related data.

Instead:
- **This repo** holds code, documentation, **codebooks**, and **summary statistics** — the
  *description* of the data.
- **The data** lives in **controlled S3 storage** and is shared via **time-limited
  presigned links** or on request.

This is a deliberate **data-hygiene + privacy** decision (and it's enforced in
`.gitignore`).

<a name="getting-the-data"></a>
## Getting the data (for judges / collaborators)

The dataset is available on request as a **time-limited presigned download link** to the
controlled S3 bucket — covering `patientpunk.db`, the schema, and (optionally) the
intermediate corpora. Ask a project maintainer for a link; they expire (max 7 days) and
can be regenerated. The links require no AWS account and grant read-only access to those
specific files only.
