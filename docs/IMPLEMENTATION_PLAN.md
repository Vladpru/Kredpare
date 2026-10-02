# Kredpare — Implementation Plan

Architecture: [architecture.html](architecture.html).

## What we are building

Every day, Kredpare reconciles files exchanged between a company and its counterparties, finds money discrepancies, and drives each discrepancy to closure: explanation, proposal, human approval, counterparty reply.

v1 covers the **lending** domain: selling loans to partners (forward flow). The core (`core/`) is domain-agnostic. A second domain (payments) is added after v1 to prove that the core really is generic.

## Principles for every iteration

- **Simplest solution first.** Every discrepancy goes through a cascade: **rules (code) → workflow (RAG + 1 LLM call) → agent → escalate**. A more complex level only receives what the simpler one could not close. The agent has to justify itself with eval numbers; it is not the default.
- **Only code computes money.** Logic for amounts, interest, and matching is written test-first and uses `Decimal`.
- **The core does not know the domain.** `core/` never imports `domains/`, enforced by `import-linter` in CI. A domain registers its own schemas, break types, rules, tools, and prompts.
- **Evals first, optimizations second.** Every AI component gets a baseline metric before it gets improved.
- **Audit from day one.** Every state change writes an event to the append-only `audit_events` table.
- **Vertical slices.** Every iteration ends with a working result you can demo: a command, an endpoint, or a screen.
- **An ADR for every significant decision** in `docs/adr/`. These later become the README "Trade-offs" section.
- **Definition of Done (DoD)** for every iteration: CI is green, new tests exist, docs are updated.

Metric thresholds below are **targets**. You record the real values after the baseline and from then on CI does not allow them to regress.

## Primary project metric

**Break closure cascade:** what share of breaks is closed by rules, by the workflow, by the agent, and how many are escalated. Plus accuracy and cost ($) at each level. These numbers are the central table of the README.

## Code structure

```
backend/src/kredpare/
├── core/                 # generic, never mentions "loan"
│   ├── ingest/           # upload, S3, header hash
│   ├── mapping/          # versioned mapping configs, LLM proposals
│   ├── matching/         # DuckDB engine
│   ├── rules/            # rule registry + runner
│   ├── rag/              # parsing, chunking, hybrid search
│   ├── cases/            # LangGraph: workflow, agent, lifecycle
│   ├── audit/            # append-only events
│   └── api/              # FastAPI routes
└── domains/
    └── lending/          # schemas, break_types, rules, tools, prompts
```

Core terminology: `counterparty` (not lender), `agreement` (not loan sale agreement), `record` (not loan).

---

## Instructions for Claude Code

This plan is executed together with Claude Code. Before starting **every** iteration, Claude:

1. Reads the **"Before starting"** block of that iteration.
2. Checks everything it can verify on its own: files exist, variables in `.env` are set (only whether they are set, never printing values), `gh auth status`, `docker info`.
3. **Asks the user** about everything it cannot verify: accounts, keys, decisions. It asks in one list, not one item at a time.
4. Does not start the iteration until every item is confirmed. If an item can be postponed, it states explicitly what that affects.

**Security:** Claude never asks for a key or password to be pasted into the chat. The user puts keys into `.env` (locally) or GitHub Secrets. Claude only checks that the variable is set.

---

## Preparation — Iteration −1 (before week 1)

**Done by the user** (Claude asks about each item and waits for confirmation):

- [ ] Anthropic API account, a **monthly spend limit**, a separate workspace for the project. Key stored in a password manager.
- [ ] LangSmith account, projects `kredpare-dev` and `kredpare-ci`.
- [ ] Embeddings provider (Voyage or OpenAI) and reranker (Cohere): accounts, spend limits.
- [ ] GitHub: 2FA, `gh auth login`, an empty public repo `kredpare` created.
- [ ] Installed: `uv`, Node LTS + `pnpm`, OrbStack or Docker, `pre-commit`, `direnv`, `duckdb` CLI.
- [ ] Editor extensions: Python, Ruff, Even Better TOML, Docker, Tailwind CSS IntelliSense.
- [ ] Claude Code: Context7 authorized via `/mcp` in a `claude` terminal (or `mcpdoc` connected with the LangGraph docs).
- [ ] LangGraph docs read: persistence, `interrupt`, `Command`, `Send`, Store.

**Done by Claude** (after the session moves to `~/Code/Kredpare`):

- [ ] `CLAUDE.md`: project rules (`Decimal` for money, test-first for money logic, `core/` never imports `domains/`, the rules → workflow → agent cascade, `make check` and `make test` commands, and a pointer to "Instructions for Claude Code" in this plan).
- [ ] `.claude/settings.json`: allowlist for `uv run pytest`, `make *`, `docker compose *`; a `ruff format` hook after editing Python files.
- [ ] `docs/adr/`: a template and ADRs for decisions already made (Python + FastAPI, Celery, pgvector, `core/` + `domains/`, the cascade).
- [ ] `docs/glossary.md`: domain terms (forward flow, funding date, accrued interest, premium/discount, purchase confirmation…).
- [ ] `docs/domain/break-taxonomy.md`: break types, difficulty level, who explains each.
- [ ] `docs/domain/canonical-schema.md`: draft of the canonical record and the lending schemas.
- [ ] `docs/domain/counterparties.md`: 3 fictional counterparties, their file formats and agreement specifics.
- [ ] `docs/evals.md`: template for metric tables.
- [ ] GitHub Project: milestones for iterations 0–10, issues for iterations 0 and 1, labels.

**DoD:** every user item is confirmed, Claude's documents are committed to the repo.

---

## GitHub: repository, process, CI/CD

The public GitHub repository is part of the portfolio. Recruiters and engineers look not only at the code but also at the commit history, PRs, CI, and issues.

### Repository and process

- **Public repo** `kredpare` from day one, MIT license.
- **Protected `main` branch:** merge only through a PR, CI must be green, no force push.
- **Every task gets its own branch and PR**, even when working solo. PR description follows a template: what changed, how it was verified, a screenshot or output for UI and evals.
- **Conventional Commits:** `feat:`, `fix:`, `test:`, `docs:`, `ci:`, `refactor:`.
- **Issues and GitHub Projects:** a Backlog → In progress → Done board. One **milestone per iteration**; the iteration's tasks are issues inside it.
- **Labels:** `iteration-N`, `core`, `domain:lending`, `ai`, `evals`, `run-evals`.
- **Releases:** a tag at the end of every iteration (`v0.1.0` after iteration 0, `v0.2.0` after 1…) with release notes. `v1.0.0` after iteration 10.
- **Templates:** `.github/pull_request_template.md`, `.github/ISSUE_TEMPLATE/` (feature, bug).
- **Security:** Dependabot (pip, npm, GitHub Actions), secret scanning and push protection, CodeQL.
- **README badges:** CI, evals, coverage, license.

### Workflows in `.github/workflows/`


| Workflow                    | Trigger                                          | What it does                                                                                                 |
| --------------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `ci.yml`                    | every PR and push to `main`                      | ruff, pyright, import-linter, pytest with service containers (postgres + pgvector, redis), coverage          |
| `web.yml`                   | PRs that change `web/`                           | lint, typecheck, build. Playwright e2e from iteration 8                                                      |
| `evals.yml`                 | `run-evals` label on a PR + nightly (`schedule`) | eval suite against LangSmith, comparison with baseline, PR comment with a metrics table, fails on regression |
| `deploy.yml`                | push to `main` after green CI                    | build Docker images → GHCR, Alembic migrations, deploy api / worker / beat to Fly.io                         |
| Vercel (GitHub integration) | every PR and `main`                              | frontend preview deployment for every PR, production from `main`                                             |


### Secrets and environments

- **GitHub Environments:** `staging` and `production`. Production deploys require manual approval.
- LLM, LangSmith, Fly, and Neon keys live only in GitHub Secrets. LLM keys are available only to `evals.yml` and `deploy.yml`.
- Nothing real in the repo: synthetic data only, `.env.example` without values.

---

## Iteration 0 — Foundation (week 1)

**Before starting (Claude asks):** Preparation (iteration −1) is complete: repo created, `gh auth status` OK, Docker running.

**Goal:** an empty but working skeleton with the right boundaries.

- **GitHub:** public repo, protected `main`, PR and issue templates, Project board, milestones for all iterations, labels, Dependabot, secret scanning.
- Monorepo: `backend/` (uv, Python 3.12), `datagen/`, `web/` (Next.js), `docs/`.
- `core/` + `domains/lending/` structure. `import-linter` contract: `core` does not import `domains`.
- ruff, pyright, pytest, pre-commit.
- `docker-compose.yml`: postgres + pgvector, redis, minio, mailpit.
- FastAPI: `GET /health` checks the DB, Redis, and S3.
- SQLAlchemy 2.0 + Alembic, first migration.
- Celery worker + Celery Beat, a test `ping` task.
- Next.js scaffold: Tailwind + shadcn/ui.
- `ci.yml` and `web.yml` (see the "GitHub" section). `deploy.yml` as a stub, enabled in iteration 10.
- `Makefile`: `make up`, `make check`, `make test`.

**DoD:** `make up && make check` is green locally and in CI. Importing a domain from `core` breaks CI. First PR merged through the protected `main`, tag `v0.1.0`.

---

## Iteration 1 — Canonical model and synthetic data (week 2)

**Before starting (Claude asks):** The user has reviewed and approved `canonical-schema.md`, `break-taxonomy.md`, and `counterparties.md`.

**Goal:** the data model and a generator with ground truth. Everything else depends on this.

- **Core:** a base canonical record: keys, amounts (`Decimal`), dates, status. A domain registration interface (`DomainSpec`): schemas, break types, rules, tools.
- **Lending:** schemas `FundedLoan`, `PurchaseConfirmation`, `ServicerOnboarding` (Pydantic + Pandera).
- 3 fictional counterparties with different formats:
  - different column names and order;
  - different date formats;
  - different amount formats (`"$1,234.50"`, cents as int).
- **Break injector** with labeled difficulty levels:
  - **simple**, closed by a rule: `missing_record`, `amount_mismatch`, `stale_pending`, `duplicate`, `date_mismatch`;
  - **medium**, needs the agreement: `accrued_interest_error` caused by an amendment; `price_grid_amendment` (an amendment changes the price for one credit tier);
  - **hard**, for the agent: the same discrepancy across all loans of one dealer; a combination of two causes; a rule change without notice.
- CLI: `kredpare-datagen --seed 42 --days 30` generates CSVs and `ground_truth.jsonl` with the cause and difficulty level.

**DoD:** property tests (Hypothesis): every injected break is in the ground truth, clean data passes validation, the same seed produces the same output.

---

## Iteration 2 — Pipeline A without LLM (weeks 3–4)

**Before starting (Claude asks):** Nothing new from the user. Claude checks that `make up` starts postgres, redis, and minio.

**Goal:** from a file to a list of breaks, with hand-written mapping.

- Tables `counterparties`, `mapping_configs`, `files`, `records`, `breaks`, `audit_events`.
- `**audit_events` is append-only:** a trigger rejects `UPDATE`/`DELETE`, plus a `prev_hash`/`hash` chain.
- `POST /files`: upload to S3 with sha256. Files are immutable; re-uploading is idempotent.
- Celery task `ingest_file`: header hash → `mapping_config` → Polars normalize → Pandera validate → Postgres. Validation errors are stored and shown, never swallowed.
- **Matching engine** on DuckDB (`core/`) with keys and comparison rules supplied by the domain. Output: typed breaks.
- Seed: hand-written mapping v1 for 3 counterparties.

**Evals (deterministic):** break detection precision and recall per type.

**DoD:** recall and precision ≥ 0.98 (target; matching is deterministic, so it should be close to 1.0). A test proves that `UPDATE audit_events` fails.

---

## Iteration 3 — LLM schema mapping + HITL #1 (week 5)

**Before starting (Claude asks):** `.env` has `ANTHROPIC_API_KEY`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT` set. The Anthropic spend limit is configured.

**Goal:** an unknown file format no longer breaks the pipeline.

- New header hash → Haiku proposes a `MappingProposal` via structured output:
  - `source_col → canonical_field`;
  - `transform` from a fixed enum (`parse_usd`, `cents_to_decimal`, `parse_date_mdy`…);
  - `confidence`.
- Only headers plus 3 sample rows with masked PII are sent to the LLM.
- `POST /mappings/{id}/approve` creates a new version, the old one becomes `superseded`, the file is reprocessed. **A proposal is never applied without approval.**
- Enable LangSmith tracing.
- The generator mutates formats: 20–30 variants.

**Evals:** mapping accuracy per field, transform accuracy separately. Record the baseline.

**DoD:** baseline in `docs/evals.md`. A test proves that a proposed config is not applied without approval.

---

## Iteration 4 — RAG over agreements (weeks 6–7)

**Before starting (Claude asks):** `.env` has embeddings and reranker keys set. The user has approved the structure of the synthetic agreements (sections, amendments, traps).

**Goal:** find the rule in force, with a citation.

- Synthetic agreements: for each counterparty, a base agreement + 2 amendments with `effective_date`. They contain defined terms, cross-references, purchase price and accrued interest formulas, and tables.
- Docling → chunking by section. Metadata: `counterparty_id`, `section_id`, `effective_date`, `supersedes`.
- Embeddings → pgvector + `tsvector`. Hybrid search via RRF, then a reranker.
- `search_agreement(query, counterparty_id, as_of_date)` returns the version of the clause in force.
- Golden set: 60–100 questions with expected `section_id`s, including amendment traps.

**Evals:** recall@5 and MRR. Experiment table:


| Variant               | recall@5 | MRR | latency | cost |
| --------------------- | -------- | --- | ------- | ---- |
| vector only           |          |     |         |      |
| hybrid (RRF)          |          |     |         |      |
| hybrid + rerank       |          |     |         |      |
| long context (no RAG) |          |     |         |      |


**DoD:** the table is filled with real numbers, plus an ADR with the chosen approach.

---

## Iteration 5 — Rules + workflow (week 8)

**Before starting (Claude asks):** The user has approved the list of lending rules and the `confidence` threshold for moving to the next cascade level.

**Goal:** the first two cascade levels. No agent.

- **Rule engine** (`core/rules/`): rule registry, runner, result `explained | not_explained`.
- **Lending rules** (`domains/lending/rules/`), test-first: missing record, difference within rounding, accrued interest from an alternative date, `stale_pending` &gt; N days, duplicate.
- **Deterministic tools**, test-first: `calc_accrued_interest`, `recompute_funding`, `query_records` (read-only SQL via a sqlglot allowlist).
- **Workflow explainer** (LangGraph, fixed steps): break → `search_agreement` → 1 LLM call → `Explanation` (root cause, citation, `confidence`).
- **Cascade:** rules → workflow → if `confidence` is below the threshold, status `needs_investigation` (the agent arrives in iteration 7).

**Evals:**

- share of breaks closed by rules and by the workflow, per difficulty level;
- root cause accuracy and citation correctness for the workflow;
- cost per break.

**DoD:** first version of the cascade table. Hard breaks honestly land in `needs_investigation` instead of getting an invented explanation.

---

## Iteration 6 — Case lifecycle (week 9)

**Before starting (Claude asks):** The user has approved the reject-loop limit (N) and the counterparty email templates. Mailpit runs in docker-compose.

**Goal:** from explanation to closure. LangGraph as the workflow orchestrator.

- `PostgresSaver` checkpointer, `thread_id` = case id.
- **HITL #2:** `interrupt()` → `POST /cases/{id}/decision` → `Command(resume=...)`.
- Decision branches:
  - **reject + comment** → explain again with the comment in state. The loop is limited to N returns;
  - **correction** → `apply` (deterministic, idempotency key) → `Store` → `resolved`;
  - **email** → draft → send (dev: Mailpit) → `wait_reply` (`interrupt`).
- `POST /cases/{id}/reply` (webhook or manual entry) resumes the graph: "confirmed" → `resolved`, "disputed" → explain again.
- Every transition writes an event to `audit_events` with `model`, `prompt_version`, `trace_id`.

**Tests:** interrupt and resume; **resume after a worker restart** (simulating a pause of days); `apply` idempotency; reject-loop limit.

**DoD:** every branch is covered by integration tests.

---

## Iteration 7 — Agent for the long tail (week 10)

**Before starting (Claude asks):** The user has approved the agent attempt limit, the budget per case ($), and the set of hard cases for the workflow vs agent comparison.

**Goal:** the third cascade level, only for `needs_investigation`.

- `Send()` fan-out over `needs_investigation` cases.
- Investigator ⇄ tools: `query_records`, `calc_*`, `search_agreement`, `find_similar_cases` (Store).
- "Found it?" router with an attempt counter. After N attempts → escalate (`interrupt()`).
- The result enters the same lifecycle from iteration 6. Reject returns the case to the investigator via `Command(goto=...)`.
- **Rule candidates:** if the agent finds the same new cause several times and a human confirms it, a "rule candidate" record is created to be moved into code manually.

**Evals:**

- **comparison on the hard set:** workflow vs agent on accuracy, cost, and latency;
- trajectory eval: whether the expected tools were called;
- updated cascade table.

**DoD:** an ADR "Does the agent justify itself?" with numbers. If the gain is small, say so.

---

## Iteration 8 — Frontend (week 11)

**Before starting (Claude asks):** The user has decided whether to deploy the frontend to production right away or only use Vercel previews for now. The Vercel account is connected to GitHub.

**Goal:** a demo without a terminal.

- TS types generated from OpenAPI (`openapi-typescript`).
- Screens:
  - file upload;
  - **breaks table** (TanStack Table; filters: counterparty, type, status, **cascade level**);
  - **case page:** who explained it (rule / workflow / agent), live steps via SSE, citation, approve / reject / comment;
  - mapping approval (HITL #1);
  - queue of escalations and cases in `wait_reply`;
  - **cascade dashboard:** shares, accuracy, cost.
- Playwright e2e for one full scenario.

**DoD:** the full scenario from upload to resolved works in the UI. e2e runs in CI.

---

## Iteration 9 — Production hardening (week 12)

**Before starting (Claude asks):** Claude Desktop is installed for MCP testing. The user has approved which fields Presidio masks.

- Model routing (Haiku/Sonnet), retries and provider fallback, rate limits in Redis.
- Semantic cache for repeated questions about agreements.
- **Presidio** masks data before it is sent to traces.
- **Prompt injection guard:** CSV and agreement content is passed as data with clear delimiters. A test with an injection inside a file field.
- **MCP server** (FastMCP): `get_breaks`, `explain_break`, `query_records`.
- Celery Beat: daily reconciliation run per counterparty.
- Cost/latency metrics: p50/p95, $ per break per cascade level, $ per daily run.

**DoD:** the injection test passes. MCP works with Claude Desktop.

---

## Iteration 10 — Evals in CI, deployment, presentation (week 13)

**Before starting (Claude asks):** Fly.io, Neon, Upstash, and Cloudflare R2 accounts are created. All keys are added to GitHub Secrets for the `staging` and `production` environments. Free tiers and spend limits are checked.

- `evals.yml` fully enabled: `run-evals` label + nightly, PR comment with metrics, fails on regression.
- `deploy.yml`: Docker images → GHCR → migrations → Fly.io (api + worker + beat). `staging` and `production` environments with manual approval.
- Infrastructure: Neon, Upstash Redis, Cloudflare R2, Vercel (preview for every PR). Secrets only in GitHub Secrets.
- README badges: CI, evals, coverage. Release `v1.0.0` with release notes.
- Demo data seed.
- README:
  - diagram;
  - **cascade table**;
  - RAG experiments and workflow vs agent;
  - trade-offs from ADRs;
  - running locally;
  - live demo and a 2-minute video.
- LinkedIn post.

**DoD:** the live demo works. Someone outside the project can run it locally by following the README.

---

## Timeline


| Weeks | Iteration                                            |
| ----- | ---------------------------------------------------- |
| 0     | −1 · Preparation: accounts, tools, domain documents  |
| 1     | 0 · Foundation + core/domains boundaries             |
| 2     | 1 · Canonical model + datagen with difficulty levels |
| 3–4   | 2 · Pipeline A                                       |
| 5     | 3 · LLM mapping + HITL #1                            |
| 6–7   | 4 · RAG over agreements                              |
| 8     | 5 · Rules + workflow                                 |
| 9     | 6 · Case lifecycle                                   |
| 10    | 7 · Agent for the long tail                          |
| 11    | 8 · Frontend                                         |
| 12    | 9 · Hardening + MCP                                  |
| 13    | 10 · CI evals + deployment                           |


Plus 1–2 weeks of buffer.

## Risks

- **Python is new.** If you fall behind, cut iteration 9 (cache, part of hardening), not evals and not the cascade.
- **Synthetic data is too easy.** Then the agent looks unnecessary only because the data is easy. The hard breaks from iteration 1 must be genuinely hard. Test them on yourself: could you solve them without running a SQL query?
- **LLM cost of evals.** Keep eval sets small and run full evals nightly.
- **Temptation to generalize.** Nothing generic "just in case". Code moves into `core/` only once it is actually needed.

## After v1


| Version | What                                                                                    | What it proves                                                             |
| ------- | --------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| v2      | **Compliance checker:** loans are checked against state laws (APR caps, fees, SCRA/MLA) | Large-scale RAG over regulations                                           |
| v3      | **Payments domain:** Stripe settlement ↔ bank statement as `domains/payments/`          | The core is generic. Criterion: minimal diff in `core/`, visible in the PR |
| v4      | Multi-tenant                                                                            | Isolation, ingestion at scale                                              |
| v5      | Fine-tune a small model on HITL corrections                                             | Data flywheel, lower cost                                                  |


