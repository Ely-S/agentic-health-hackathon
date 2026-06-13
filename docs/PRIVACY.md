# Privacy & Re-identification Risk

This document states plainly how the data is anonymized, the honest limits of that
anonymization, and why we believe the project adds **negligible re-identification risk
beyond what already exists** for content that was publicly posted on Reddit.

## The claim, up front

> The underlying posts are **already public** on Reddit. We replace usernames with hashes,
> collect no new personal information, and keep the assembled dataset under controlled
> access. We therefore **create no new identifying information** and add only a small,
> bounded, and mitigated increment over the risk that already exists for public Reddit
> content.

## 1. Baseline: the source is already public

Every post and comment in this dataset was **voluntarily and publicly posted** on Reddit
and is **publicly archived** (via Arctic Shift). Anyone today can read these posts, search
them, and link them to the account that wrote them. That is the **pre-existing
identification risk** — and it exists with or without this project.

Our standard is therefore *marginal* risk: does assembling this dataset make
re-identification **meaningfully easier** than the already-public source? We argue it does
not, materially, and we take steps to keep it that way.

## 2. What we do to reduce risk

- **Pseudonymization.** Reddit usernames are replaced with a SHA-256 hash (`author_hash`)
  at ingest. Usernames are not carried into the structured dataset, the codebooks, or any
  shared artifact.
- **No new personal data is collected.** We extract only health-topic content that the
  user themselves wrote publicly. There are **no real names, no contact details, no
  precise addresses, no account metadata**. "Location" fields are only the
  country/state a user *chose to state publicly* in a post.
- **Controlled access (defense in depth).** The assembled data (`patientpunk.db`, raw
  text, intermediates) is **never committed** to this public repository. It lives in
  controlled S3 storage and is shared via **time-limited presigned links**. During active
  judging a single such link to the database is published in the README so judges can
  evaluate without an access request; it is **time-limited (expires within 7 days) and
  revoked afterward**. The data itself never enters git history, and no permanent public
  copy is created. This repo otherwise contains only *descriptions* of the data (codebooks,
  summary statistics).
- **De-identified-by-default artifacts.** The codebooks and summary statistics published
  here are **aggregate** — counts, coverage, category labels — with no per-patient rows
  and no free text.

## 3. The honest limits (what the hashing does *not* do)

We are not claiming strong, irreversible anonymization, and we won't overstate it:

- **The username hash is unsalted SHA-256, which is reversible by dictionary attack.**
  Anyone who already holds a list of candidate usernames could hash them and match. But
  note what that implies: to "de-anonymize" via the hash you must **already know the
  username** — at which point you could simply read that user's public posts directly. The
  hash protects against *casual* handle lookup; it is not a cryptographic guarantee, and
  we don't present it as one.
- **Aggregation can fingerprint a verbose user.** Combining one author's many posts into a
  single profile (conditions + drugs + demographics) is more *fingerprint-able* than any
  single post. However, that information is **already present and public in that user's
  own posts** — aggregation reorganizes public content; it does not reveal anything the
  user did not already publish.

## 4. Residual risk assessment

The marginal risk over baseline reduces to **convenience of search/aggregation**, and it
is bounded and mitigated:

- The only way to tie a record back to a person still requires **starting from the public
  Reddit identity** (the same starting point that already exists today).
- We add **no off-Reddit linkage**, no names, no contact info — nothing that bridges to a
  real-world identity beyond what the user themselves posted.
- The assembled dataset is **not openly published**; controlled access removes the
  "crawlable, permanent, one-click-searchable" failure mode.
- Published repo artifacts are **aggregate only**.

Given all of the above, we assess the **incremental** re-identification risk of this
project as **negligible relative to the already-existing risk** of the public source
posts, for a topic (chronic illness) where we nonetheless treat the data with care.

## 5. What we deliberately do *not* do

- We do **not** publish usernames or any mapping from `author_hash` back to a username.
- We do **not** commit raw text, the database, or per-patient rows to this (or any) public
  repository.
- We do **not** attempt to link users to external identities or de-anonymize anyone.
- We do **not** present this data as clinical, validated, or suitable for individual
  medical decisions.

## 6. If stronger guarantees are needed

If the dataset is ever to be shared more broadly than controlled access, the
straightforward hardening is to **re-hash usernames with a secret salt** (removing the
dictionary-attack path) and to consider suppressing or coarsening rare, highly specific
free-text values. For the current scope — controlled access, aggregate public artifacts —
the measures above are, in our judgment, proportionate.
