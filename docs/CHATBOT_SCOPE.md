# Scope — data-grounded chatbot for "Patients Like Me"

A conversational assistant docked in the dashboard that **understands the data the user is
currently seeing** (their profile + per-drug-class predictions + similar-patient cohort + quotes +
literature) and lets them **ask about it** — grounded, citing the numbers/quotes, **never
prescribing**. It embodies the repo ethos: *show what patients reported, not recommend; trust
negatives over soft positives; self-report, not medical advice.*

---

## Should we refactor first? → **MINIMAL. ~300 LOC — and it's the chatbot's own scaffolding, not a rewrite.**

The codebase is **~70% ready**. You do **not** need to refactor existing code:
- The **8 query functions** (`predict`, `treatment_evidence`, `keyword_search`, `comorbidity`,
  `lit_search`, `get_post_detail`, `get_user_posts`, `explain`) are already clean, typed
  (Pydantic), and **callable in-process** — ready-made tools.
- `shared_decision/orchestrator.py` already uses **Protocol-based backends with explicit
  missing-capability reporting** — exactly the spine a truth-grounded agent wants.
- `evidence.py:_llm()` / `_llm_endpoint()` (xAI Grok + OpenRouter DeepSeek, deterministic fallback)
  is a **reusable LLM layer**.

What you DO add are **three thin layers the chatbot needs anyway** (~300 LOC total):
1. **`ChatbotQueryService`** (~100 LOC, `backend/search_api/chatbot.py`) — one typed facade over the
   8 functions, so the agent and the routes share a single validated path (no duplicated SQL, one
   set of safety gates).
2. **`ConversationContext`** (~80 LOC, `shared_decision/models.py`) — multi-turn state: profile,
   turn history, last evidence, pending clarifications. (Keeps state out of raw LLM memory.)
3. **`SafetyFilter`** (~120 LOC, `shared_decision/safety.py`) — enforce `SafetyPolicy` at **runtime**
   on every LLM output (block prescriptive language, append disclaimers, reject unsupported claims).
   Today `SafetyPolicy` is a *static annotation*, not enforced — for a health chatbot this must be
   runtime.

**Do NOT block on the bigger data-quality debt** (condition canonicalization incomplete; EDS/MCAS
split across fields; sentiment over-call not validated for uniformity). It **bounds what the bot can
truthfully say** — so the bot must surface uncertainty on cohort questions and trust negatives over
soft positives — but it does **not** block building. Log these as "Known Chatbot Limitations" in
`CONTINUITY.md`.

---

## Architecture (framework-agnostic core)

```
 Frontend chat widget (sidebar / modal)  ──POST /api/chat──▶  conversation loop
   passes on-screen state per message:                          │
     { profile:{conditions,severity}, predictions[] }           ├─ system prompt  (grounding + safety discipline)
                                                                 ├─ tools ─▶ ChatbotQueryService ─▶ the 8 fns ─▶ patientpunk.db / PubMed
                                                                 ├─ ConversationContext  (multi-turn state)
                                                                 └─ SafetyFilter  (runtime output gate)
```

- **Tools (5–8)** over `ChatbotQueryService`: `get_prediction`, `get_treatment_evidence`,
  `get_quote_context(post_id)`, `get_comorbidity`, `lit_search`, `get_explain`,
  `acknowledge_missing_data`. Thin wrappers — no reimplemented logic.
- **`POST /api/chat`**: `{message, conversation_id, profile, current_predictions}` →
  `{assistant_message, sources, disclaimers, updated_context}`. **Stateless server-side** (client
  manages thread → privacy).
- **Screen-context grounding**: the frontend passes the user's current profile + rendered
  predictions in each message; the bot re-validates tool calls against that profile (and flags if
  the user changed it off-screen).
- **Build location**: `src/agentic_health_hackathon/chatbot/` (imports from `shared_decision` +
  `search_api`), with a `shared-decision-chat` Typer CLI for testing.

---

## The build decision: Rumi vs native tool-loop  *(the #1 open choice)*

The core above (service + tools + context + safety) is **identical either way** — only the loop
*driver* differs, so this is a **low-lock-in, swappable** choice.

| | **Native OpenAI-SDK tool loop** *(recommended for this repo)* | **Rumi Dervish** |
|---|---|---|
| Dep | none new — reuses the existing `_llm` layer | a cross-repo dep on Rumi (not on PyPI → pin the git/local `../Rumi`) |
| Providers | keeps **xAI Grok + OpenRouter** | **OpenRouter-only** (drops xAI) |
| Fit | ~80-LOC loop; matches the repo's existing OpenAI-compatible pattern | a chatbot is literally what Rumi is for (Dervish + `@tool` + tablet-memory + whirl's tool loop) |
| Effort | write the loop + memory (small; `ConversationContext` holds state) | framework gives the loop + memory for free |

**Lean: native for this repo** — simpler, no coupling, keeps provider flexibility. Choose **Rumi** if
standardizing on it across your projects matters more than xAI + zero new deps. Either way the tools
and grounding are the same, so you can swap later.

---

## Data grounding + safety  *(the heart of it)*

"Understand the data presented" = the bot receives the on-screen **profile + predictions** as
context and has **tools** to fetch the supporting cohort/quotes/literature on demand. Discipline:

- **Cite every number** — *"71% positive (95% CI 64–77%), from 203 reports"*, never "most".
- **Show, don't recommend** — reframe *"should I take X?"* → *"patients with your profile reported
  N% positive on X; here's what they said."*
- **Trust negatives over soft positives**; distinguish confidence tiers (n≥150 "good" vs limited);
  surface quote availability (*"quotes from 12 similar patients"* vs *"none in your cohort"*).
- **Never extrapolate, never claim safety** — *"I can't tell you if it's safe; I show what patients
  reported. Discuss with your doctor."*
- **Refuse to prescribe** — the `SafetyFilter` blocks prescriptive output at runtime.

**Example Q&A (grounded):**
- *"Why is autonomic 96% for me?"* → `get_prediction` → cites the %, CI, n, and the drivers
  (POTS ↑, mobility-limited ↑), tags confidence tier.
- *"Which patients like me tried LDN?"* → `get_treatment_evidence` → "43 of your 156-patient cohort
  reported on LDN: 28 positive / 12 negative / 3 mixed" + 2 real quotes (with `post_id`), caveat.
- *"Is antihistamine safe for me?"* → refuses the safety question, pivots to the reported signal +
  "decision-support input for a conversation with your doctor."
- *"Just tell me what to take."* → declines; offers to show the evidence for a class instead.

---

## Effort + sequence
1. The 3 thin layers (~300 LOC): `ChatbotQueryService`, `ConversationContext`, `SafetyFilter`.
2. The tools + the conversation loop (native or Rumi) + the system prompt.
3. `POST /api/chat` + the frontend widget + screen-context passing.
4. **Safety/grounding tests** — adversarial "tell me what to take / is this safe" prompts; an
   every-number-is-cited audit; empty-cohort / limited-confidence / profile-changed-mid-chat edges.

**≈ 1–2 focused days for an MVP** — the heavy lifting (the data, the models, the 8 APIs) already exists.

## Open choices
1. **Framework** — native (rec.) vs Rumi.
2. **Widget placement** — right sidebar (in-context) vs floating modal (no layout change) vs a
   separate `/chat` page.
3. **Spine** — call `ChatbotQueryService` directly now, or wire it through the existing
   `shared_decision` orchestrator from the start.
