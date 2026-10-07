# Kredpare — MVP Plan

Source of truth for scope, order, and Definition of Done **until the MVP verdict** (step M4). After that, work continues from [POST_MVP_PLAN.md](POST_MVP_PLAN.md). The original full plan, [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md), stays as the reference for the design of every component. Decision: [ADR 0008](adr/0008-mvp-before-full-plan.md).

## Why an MVP

The full plan takes about 13 weeks before it shows whether the core idea works. The MVP tests the riskiest assumption first, on the synthetic data and ground truth from Iteration 1:

> **Hypothesis:** deterministic rules plus **one** LLM call that reads the agreement can explain most reconciliation breaks correctly, with a citation, at low cost. Breaks they cannot explain are routed to a human honestly, never with an invented explanation.

If the hypothesis holds, the expensive parts (RAG, case lifecycle, agent, deployment) are worth building. If it fails, the eval numbers show which layer is weak before months are spent on the rest.

## Already done (Iterations 0–1 of the full plan)

- Foundation: monorepo, CI, docker compose, FastAPI `/health`, SQLAlchemy + Alembic, Celery, Next.js scaffold.
- Canonical model: `CanonicalRecord`, `DomainSpec`, lending schemas, `validate_frame` (Pydantic row rules, Pandera file shape).
- Lending pricing math: day counts, accrued interest, purchase price.
- `kredpare-datagen`: 3 buyers + servicer, each party's file format, 12 injected causes, `ground_truth.jsonl`, `manifest.jsonl`, property tests.

## Success criteria (fixed before M1, checked in M4)

Confirmed by the user on 2026-10-05 and recorded in `docs/evals.md` (issue #43). They are not changed after measurements start.

| # | Criterion | Target |
|---|---|---|
| S1 | Break detection precision and recall, every break type | ≥ 0.98 |
| S2 | Share of **simple** breaks closed by rules | ≥ 0.90 |
| S3 | Rules never claim a medium or hard break | 0 false explanations |
| S4 | **Medium** breaks: root cause accuracy of the workflow | ≥ 0.80 |
| S5 | **Medium** breaks: citation accuracy (amendment and section in force) | ≥ 0.80 |
| S6 | **Hard** breaks routed to `needs_investigation`, not explained | ≥ 0.90 |
| S7 | LLM cost per break that reaches the workflow | ≤ $0.01 |
| S8 | A reviewer can go from a break to approve or reject in the UI without a terminal | yes / no |

**Verdict rule:** S1–S3 are engineering gates (deterministic; failing them is a bug to fix, not a verdict). S4–S7 decide the hypothesis. S8 decides whether the product is demonstrable.

## Principles kept from the full plan

All non-negotiable rules in `CLAUDE.md` apply unchanged: `Decimal` money, only code computes money, money logic test-first, `core/` never imports `domains/`, the rules → workflow → agent cascade (the agent level is simply not built in the MVP), audit from day one, no proposal applied without human approval, evals first, synthetic data only.

## Explicitly out of scope for the MVP

| Not in MVP | Why it can wait | Comes back in |
|---|---|---|
| S3 upload, `POST /files`, Celery ingest, Beat schedule | Files come from local `kredpare-datagen` output; ingest is a CLI | Post-MVP P1 |
| `audit_events` hash chain (`prev_hash` / `hash`) | Append-only trigger is enough to prove the rule | P1 |
| LLM schema mapping, HITL #1, format mutations | Hand-written mappings for 4 known formats | P2 |
| RAG (Docling, embeddings, hybrid search, reranker) | Agreements are short; the whole text fits in the prompt (the plan's "long context" baseline) | P3 |
| LangGraph case lifecycle, corrections apply, emails, replies | Approve/reject is only recorded, nothing is applied or sent | P4 |
| Agent for hard breaks | Hard breaks go to `needs_investigation`; that is the honest MVP outcome | P5 |
| Full frontend (SSE, mapping screen, dashboards, e2e) | One table and one detail page are enough to judge the idea | P6 |
| Model routing, caching, Presidio, MCP, rate limits | Hardening, not validation | P7 |
| LangSmith, `evals.yml`, deployment, Vercel | Evals run locally; deterministic evals run in CI | P8 |

## Instructions for Claude Code

Same as the full plan. Before starting **every** step, Claude:

1. Reads the step's **"Before starting"** block.
2. Checks everything it can verify itself: files exist, `.env` variables are set (never printing values), `docker info`, `make up`.
3. Asks the user about everything else **in one list**.
4. Does not start until every item is confirmed. If an item can be postponed, it states what that affects.

Claude never asks for a key to be pasted into the chat. Each step is one milestone; each issue is one branch and PR, grouped as the user prefers.

---

## M1 — Ingest and matching (weeks 1–2)

**Before starting (Claude asks):** The success criteria are fixed (done 2026-10-05). Claude checks that `make up` starts postgres and that `alembic upgrade head` runs.

**Goal:** from a `kredpare-datagen` output directory to a list of typed breaks in Postgres, with no LLM.

- **Tables** (Alembic): `counterparties`, `mapping_configs`, `files`, `records`, `row_errors`, `breaks`, `audit_events`.
- **`audit_events` is append-only:** a trigger rejects `UPDATE` and `DELETE`. Every state change below writes an event.
- **Transforms** (`core/mapping/`), test-first, from a fixed enum: `parse_usd`, `cents_to_decimal`, `parse_decimal`, `percent_to_fraction`, `parse_date_iso`, `parse_date_mdy`, `parse_date_ymd_compact`, `parse_date_dmon_y`. A value that would need rounding is an error, never rounded.
- **Hand-written mapping configs v1** for the seller, Quillmont, Brackwater, Tessaline, and Orlo, stored in `mapping_configs`, keyed by a hash of the header row.
- **CLI** `kredpare ingest <dir>`: reads `manifest.jsonl`, checks sha256, finds the mapping by header hash, normalizes with Polars, runs `validate_frame`, stores valid records and row errors. Re-ingesting the same file is idempotent (same sha256 → no duplicate rows). Unknown header → the file is stored as `unmapped`, never guessed.
- **Matching engine** (`core/matching/`, DuckDB): reads `MatchDeclaration`s from `DomainSpec`; emits `missing_record`, `duplicate`, `amount_mismatch`, `date_mismatch`, and `stale_pending` (N business days after cut-off at the as-of date; N and the business-day calendar come from the domain). One break per (record, field). Matching never decides the cause.
- **CLI** `kredpare match --as-of <date>`.

**Evals (deterministic):** `kredpare eval matching <dir>` expands `ground_truth.jsonl` (`loan_ids × fields`) and reports precision and recall per break type. Results go to `docs/evals.md`. CI runs this eval on a seed and fails below the target.

**DoD:** S1 met on seed 42 and on 3 other seeds. A test proves `UPDATE audit_events` fails. A test proves re-ingest is idempotent. `make check && make test` green.

---

## M2 — Rules: the first cascade level (week 3)

**Before starting (Claude asks):** The user approves the rule list: one rule per simple cause in `docs/domain/break-taxonomy.md` (`loan_not_confirmed`, `loan_not_offered`, `duplicate_row`, `confirmation_overdue`, `settlement_date_roll`, `rounding_difference`, `accrual_start_alternative`).

**Goal:** code closes simple breaks with an exact, reproducible explanation.

- **Rule engine** (`core/rules/`): registry from `DomainSpec.rules`, runner, result `explained | not_explained`. An explanation stores the rule name, cause, wrong side, proposal kind (`correction` or `email`), and the evidence (recomputed values).
- **Lending rules** (`domains/lending/rules/`), test-first, one per simple cause. A rule explains a break only when recomputation reproduces the counterparty value **exactly**; otherwise `not_explained`.
- **Deterministic tools** (`domains/lending/tools/`): `calc_accrued_interest` and `recompute_purchase_price` over `pricing.py`; `query_records` (read-only, parameterized, no free SQL yet).
- **Cascade runner** `kredpare explain`: rules first; unexplained breaks get status `pending_workflow`.

**Evals:** share of simple breaks closed by rules (S2), cause accuracy of rule explanations, and false explanations on medium and hard breaks (S3). First row of the cascade table in `docs/evals.md`. CI fails if S2 or S3 regress.

**DoD:** S2 and S3 met. Cascade table row "Rules" filled with real numbers.

---

## M3 — Workflow: one LLM call with the agreement (weeks 4–5)

**Before starting (Claude asks):** `.env` has `GEMINI_API_KEY` set (provider decision: [ADR 0011](adr/0011-gemini-for-workflow-llm.md)). The user approves the synthetic agreement texts (structure, sections, amendments, the RAG traps from `counterparties.md`) and the `confidence` threshold for `needs_investigation` (proposal: 0.7).

**Goal:** the second cascade level explains medium breaks with a citation; hard breaks are routed to a human.

- **Synthetic agreements** (`domains/lending/agreements/`): markdown for each buyer, base agreement + 2 amendments, with `effective_date`, the section numbering from `counterparties.md`, and the traps (effective date vs batch date, not yet in force, numbering vs effective order, renumbered sections, no clause at all).
- **Workflow explainer** (a plain function, no LangGraph yet). The generic flow lives in `core/cases/`; the domain supplies the candidate tools, the prompt, and the agreement documents through `DomainSpec`:
  1. Code gathers the break, both rows, and the counterparty's agreement documents with their effective dates.
  2. Code precomputes candidate values with deterministic tools (each day count, each pricing grid version in the documents, inclusive or exclusive end) and passes them as data. **The LLM never computes an amount;** it chooses among computed candidates and cites the clause.
  3. One LLM call with structured output: `Explanation(cause, wrong_side, citations, proposal, confidence, reasoning)`.
  4. `confidence` below the threshold, or no candidate reproduces the value → `needs_investigation`.
- Agreement and file content is passed as data inside clear delimiters (basic prompt-injection hygiene).
- Every call writes an audit event with `model`, `prompt_version`, tokens, and cost.
- Model choice is an eval result, not an assumption: run the medium set on `gemini-3.5-flash-lite` and on `gemini-3.5-flash`, record both ([ADR 0011](adr/0011-gemini-for-workflow-llm.md)).

**Evals:** `kredpare eval workflow <dir>`: root cause accuracy (S4), citation accuracy (S5), wrong-side accuracy, share of hard breaks routed to `needs_investigation` (S6), cost per break (S7), p50/p95 latency. Results cached by input hash so reruns are free. Baseline recorded in `docs/evals.md`, including the "long context" row of the RAG table.

**DoD:** baseline recorded with real numbers for both models. Cascade table row "Workflow" filled. A test proves a hard break with no supporting clause is not given an invented explanation.

---

## M4 — Review screen and MVP verdict (week 6)

**Before starting (Claude asks):** The user decides who judges the MVP: the user alone, or also outside reviewers (for example, reconciliation analysts). This sets how polished the screens must be. Claude checks `cd web && pnpm build` passes.

**Goal:** a person can review breaks and explanations without a terminal, and the MVP gets a written verdict.

- **API:** `GET /breaks` (filters: counterparty, break type, status, cascade level), `GET /breaks/{id}` (both rows, explanation, citation with the clause text), `POST /breaks/{id}/decision` (`approve` or `reject` with a comment). A decision is recorded in `audit_events`; **nothing is applied or sent.**
- **Web** (Next.js, TS types from OpenAPI): breaks table, break page with the two rows side by side, the explanation, who explained it (rule or workflow), the cited clause, and approve / reject.
- `make demo`: `make up` → migrations → `kredpare-datagen` → `ingest` → `match` → `explain` → API and web running.
- **Verdict:** an ADR (next free number, `NNNN-mvp-verdict.md`) with the success criteria table filled with measured values, what worked, what failed, and the decision: continue with the post-MVP plan as is, continue with changes, or stop.

**DoD:** `make demo` works from a clean checkout following the README. S8 checked by the chosen reviewers. Verdict ADR merged.

---

## Timeline

| Weeks | Step |
|---|---|
| 1–2 | M1 · Ingest and matching |
| 3 | M2 · Rules |
| 4–5 | M3 · Workflow with long-context agreements |
| 6 | M4 · Review screen and verdict |

Plus up to 1 week of buffer. If behind schedule, cut M4 polish, never evals.

## Risks

- **Synthetic data is too easy or too hard for the LLM.** Results only mean something if the medium set needs the agreement. Check by hand that a medium break cannot be explained without reading the amendment in force.
- **Precomputed candidates make the LLM's job trivial.** That is acceptable: the hypothesis is about the cascade, and "code computes, LLM chooses and cites" is the intended design. Record it in the verdict.
- **Long context hides the retrieval problem.** Three short agreements fit easily. The verdict must say how the approach would scale to long agreements; RAG (P3) is the planned answer.
- **Success criteria drift.** Targets are fixed before M1 and are not edited after measurements start.
