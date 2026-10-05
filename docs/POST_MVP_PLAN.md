# Kredpare — Post-MVP Plan

The rest of v1, after the MVP verdict ([MVP_PLAN.md](MVP_PLAN.md), step M4). It covers everything in the original [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) that the MVP deliberately left out. The design detail of each component stays in the original plan; this document sets the order, the gates, and what changes because the MVP already exists.

## Gate

Nothing here starts before the MVP verdict ADR is merged.

| Verdict | What happens |
|---|---|
| **Continue** | Phases P1–P8 in the order below. |
| **Continue with changes** | The verdict ADR names the weak layer. Fix it first (for example: better candidates for the workflow, a different model, more rules), re-measure, then start P1. |
| **Stop** | Archive this plan. The repo stays as a portfolio piece with the measured MVP results in the README. |

## Order and why

Phases are ordered by **risk to the product first, polish last**. Each phase ends with something demonstrable and updates `docs/evals.md`.

| Phase | Original iteration | Weeks | Depends on |
|---|---|---|---|
| P1 · Production ingest | 2 (remainder), 9 (Beat) | 1 | MVP |
| P2 · LLM schema mapping + HITL #1 | 3 | 1 | P1 |
| P3 · RAG over agreements | 4 | 2 | MVP (M3 baseline) |
| P4 · Case lifecycle | 6 | 1 | MVP |
| P5 · Agent for the long tail | 7 | 1 | P3, P4 |
| P6 · Full frontend | 8 | 1 | P2, P4, P5 |
| P7 · Production hardening + MCP | 9 | 1 | P5 |
| P8 · Evals in CI, deployment, presentation | 10 | 1 | all |

About 9 weeks plus buffer. P3 and P4 are independent and can swap if the MVP verdict says the lifecycle matters more than retrieval.

## Instructions for Claude Code

Unchanged: before every phase, Claude reads its "Before starting" block, verifies what it can, asks the user about the rest in one list, and waits for confirmation. Keys are never pasted into the chat.

---

## P1 — Production ingest (week 1)

**Before starting (Claude asks):** Nothing new from the user. Claude checks that `make up` starts postgres, redis, and minio.

**Goal:** files arrive through the API instead of a local directory, and the daily run is scheduled.

- `POST /files`: upload to S3 (MinIO locally) keyed by sha256. Files are immutable; re-uploading is idempotent. Upload metadata carries `counterparty_id` and `batch_id`.
- Celery task `ingest_file` wraps the MVP's ingest code unchanged: header hash → `mapping_config` → Polars normalize → `validate_frame` → Postgres.
- `audit_events` hash chain: `prev_hash` / `hash` per event, plus a verification command.
- Celery Beat: a daily reconciliation run per counterparty (ingest what arrived → match → explain).
- The MVP CLI keeps working on top of the same functions.

**DoD:** an uploaded datagen directory reaches the same breaks as the MVP CLI (same eval numbers). A test proves a tampered audit event breaks the chain.

---

## P2 — LLM schema mapping + HITL #1 (week 2)

**Before starting (Claude asks):** `.env` has `LANGSMITH_API_KEY` and `LANGSMITH_PROJECT` set. Anthropic spend limit still configured.

**Goal:** an unknown file format no longer stops the pipeline. As in original Iteration 3.

- New header hash → the LLM proposes a `MappingProposal` (`source_col → canonical_field`, `transform` from the MVP's fixed enum, `confidence`). Only headers plus 3 sample rows with masked values are sent.
- `POST /mappings/{id}/approve` creates a new version; the old one becomes `superseded`; the file is reprocessed. **A proposal is never applied without approval.**
- Datagen mutates formats: 20–30 variants (renamed and reordered columns, new date formats).
- LangSmith tracing enabled from here on.

**Evals:** mapping accuracy per field, transform accuracy separately. Baseline in `docs/evals.md`.

**DoD:** baseline recorded. A test proves a proposed config is not applied without approval.

---

## P3 — RAG over agreements (weeks 3–4)

**Before starting (Claude asks):** `.env` has the embeddings (Google AI Studio) and reranker (Cohere) keys set. The user approves the longer synthetic agreements (defined terms, cross-references, formulas, tables) that make retrieval necessary.

**Goal:** find the clause in force with a citation, for agreements too long to put whole into a prompt. As in original Iteration 4.

- Longer agreements generated from the MVP's markdown agreements, keeping the same section ids and traps.
- Docling → chunking by section; metadata `counterparty_id`, `section_id`, `effective_date`, `supersedes`.
- Embeddings → pgvector + `tsvector`; hybrid search via RRF, then a reranker.
- `search_agreement(query, counterparty_id, as_of_date)` returns the version of the clause in force.
- The MVP workflow switches from "whole agreement in the prompt" to `search_agreement` only if the eval table says so.
- Golden set: 60–100 questions with expected `section_id`s, including the amendment traps.

**Evals:** recall@5, MRR, latency, cost. The experiment table starts with the **long context row measured in M3**:

| Variant | recall@5 | MRR | latency | cost |
|---|---|---|---|---|
| long context (MVP M3) | | | | |
| vector only | | | | |
| hybrid (RRF) | | | | |
| hybrid + rerank | | | | |

**DoD:** table filled with real numbers; ADR with the chosen approach; workflow accuracy (S4, S5) does not regress.

---

## P4 — Case lifecycle (week 5)

**Before starting (Claude asks):** The user approves the reject-loop limit (N) and the counterparty email templates. Mailpit runs in docker compose.

**Goal:** from explanation to closure. As in original Iteration 6, built on the MVP's decision endpoint.

- LangGraph with the `PostgresSaver` checkpointer, `thread_id` = case id. The MVP workflow function becomes a node; its behavior and evals stay the same.
- HITL #2: `interrupt()` → `POST /cases/{id}/decision` → `Command(resume=...)`. The MVP's decision endpoint is migrated, not duplicated.
- Branches: **reject + comment** → explain again with the comment (limited to N returns); **correction** → `apply` (deterministic, idempotency key) → `resolved`; **email** → draft → send (Mailpit) → `wait_reply`.
- `POST /cases/{id}/reply` resumes the graph: "confirmed" → `resolved`, "disputed" → explain again.
- Every transition writes an audit event with `model`, `prompt_version`, `trace_id`.

**Tests:** interrupt and resume; resume after a worker restart; `apply` idempotency; reject-loop limit.

**DoD:** every branch covered by integration tests.

---

## P5 — Agent for the long tail (week 6)

**Before starting (Claude asks):** The user approves the agent attempt limit, the budget per case ($), and the hard set for the workflow vs agent comparison.

**Goal:** the third cascade level, only for `needs_investigation`. As in original Iteration 7.

- `Send()` fan-out over `needs_investigation` cases.
- Investigator ⇄ tools: `query_records` (now read-only SQL through a sqlglot allowlist), `calc_*`, `search_agreement`, `find_similar_cases`.
- "Found it?" router with an attempt counter; after N attempts → escalate (`interrupt()`).
- Results enter the P4 lifecycle. Rule candidates: a cause found several times and confirmed by a human becomes a "rule candidate" to move into code by hand.

**Evals:** workflow vs agent on the hard set (accuracy, cost, latency); trajectory eval; updated cascade table.

**DoD:** ADR "Does the agent justify itself?" with numbers. If the gain is small, say so.

---

## P6 — Full frontend (week 7)

**Before starting (Claude asks):** The user decides whether to deploy the frontend to production right away or use only Vercel previews for now. The Vercel account is connected to GitHub.

**Goal:** the whole product without a terminal. Extends the MVP's two screens. As in original Iteration 8.

- File upload; mapping approval (HITL #1); case page with live steps via SSE; queue of escalations and cases in `wait_reply`; cascade dashboard (shares, accuracy, cost).
- Breaks table gains the agent level and lifecycle statuses.
- Playwright e2e for one full scenario, run in CI.

**DoD:** upload → resolved works in the UI; e2e green in CI.

---

## P7 — Production hardening + MCP (week 8)

**Before starting (Claude asks):** Claude Desktop is installed for MCP testing. The user approves which fields Presidio masks.

As in original Iteration 9: model routing (Haiku/Sonnet) with retries and fallback, rate limits in Redis, a semantic cache for repeated agreement questions, Presidio masking before traces, a prompt-injection test with an injection inside a file field, an MCP server (`get_breaks`, `explain_break`, `query_records`), and cost/latency metrics (p50/p95, $ per break per level, $ per daily run).

**DoD:** the injection test passes; MCP works with Claude Desktop.

---

## P8 — Evals in CI, deployment, presentation (week 9)

**Before starting (Claude asks):** Fly.io, Neon, Upstash, and Cloudflare R2 accounts exist; keys are in GitHub Secrets for `staging` and `production`; free tiers and spend limits are checked.

As in original Iteration 10: `evals.yml` (label + nightly, PR comment, fails on regression); `deploy.yml` (GHCR → migrations → Fly.io api + worker + beat, manual approval for production); Neon, Upstash, R2, Vercel previews; README with diagram, cascade table, RAG and agent experiments, trade-offs, local run, live demo and video; release `v1.0.0`.

**DoD:** the live demo works; someone outside the project can run it locally from the README.

---

## After v1

Unchanged from the original plan:

| Version | What | What it proves |
|---|---|---|
| v2 | Compliance checker: loans checked against state laws (APR caps, fees, SCRA/MLA) | Large-scale RAG over regulations |
| v3 | Payments domain: Stripe settlement ↔ bank statement as `domains/payments/` | The core is generic: minimal diff in `core/` |
| v4 | Multi-tenant | Isolation, ingestion at scale |
| v5 | Fine-tune a small model on HITL corrections | Data flywheel, lower cost |
