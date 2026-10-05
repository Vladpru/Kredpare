# Kredpare

Daily reconciliation of files exchanged between a company and its counterparties. Finds money discrepancies ("breaks") and drives each one to closure: explanation, proposal, human approval, counterparty reply. v1 domain: lending (forward flow loan sales).

## Source of truth

- `docs/MVP_PLAN.md` is the source of truth for scope, order, and Definition of Done **until the MVP verdict** (step M4). After the verdict: `docs/POST_MVP_PLAN.md`. See ADR 0008.
- `docs/IMPLEMENTATION_PLAN.md` is the original full plan: the reference for component design, not for order. Iterations 0–1 from it are done.
- Before starting **every** step or phase, follow the active plan's section **"Instructions for Claude Code"**: read the step's "Before starting" block, verify what you can, ask the user about the rest in one list, and do not start until every item is confirmed.
- `docs/architecture.html` is a visual board that predates the rules → workflow → agent cascade and uses older names (`partners`, `loans`, `contract`, `query_loans`, `search_contract`). Where it conflicts with the plan, the plan wins.
- Domain docs: `docs/glossary.md`, `docs/domain/*.md`. Decisions: `docs/adr/`. Eval results: `docs/evals.md`.

## Non-negotiable rules

- **Money is `Decimal`.** Never `float` for amounts, rates, or interest. Quantize explicitly and state the rounding mode.
- **Only code computes money.** LLMs never calculate amounts, interest, or matches. They call deterministic tools.
- **Money logic is test-first.** Write the failing test before amount, interest, matching, or rule code.
- **`core/` never imports `domains/`.** Enforced by `import-linter` in CI. A domain registers its schemas, break types, rules, tools, and prompts through `DomainSpec`.
- **Core terminology is generic:** `counterparty` (not lender/partner), `agreement` (not contract / loan sale agreement), `record` (not loan). Lending words live only in `domains/lending/`.
- **Cascade for every break: rules (code) → workflow (RAG + 1 LLM call) → agent → escalate.** A higher level only receives what the lower one could not close. Do not route to the agent by default; the agent must justify itself with eval numbers.
- **Audit from day one.** Every state change writes an event to the append-only `audit_events` table.
- **No proposal is applied without human approval** (mapping configs, corrections, emails).
- **Evals first.** Every AI component gets a baseline in `docs/evals.md` before it is optimized. CI must not regress recorded metrics.
- **Synthetic data only.** No real people, companies, loans, or employer code. `.env.example` contains no values.
- **Nothing generic "just in case".** Code moves into `core/` only when it is needed.

## Commands

Available from Iteration 0 onward (the `Makefile` does not exist before then):

- `make up` — start postgres + pgvector, redis, minio, mailpit (docker compose).
- `make check` — ruff, pyright, import-linter.
- `make test` — pytest.
- Narrow test: `uv run pytest path/to/test_file.py::test_name`.
- `uv run kredpare-datagen --seed 42 --out <dir>` — synthetic files + ground truth.
- `uv run kredpare ingest <dir>` / `uv run kredpare match --as-of <date>` — load files, detect breaks (dev database).
- `uv run kredpare eval matching <dir> --as-of 2026-09-08` — break detection eval in a temporary database.

Run the narrowest relevant test first, then `make check && make test` before declaring work done.

## Layout

```
backend/src/kredpare/
├── core/      # generic: ingest, mapping, matching, rules, rag, cases, audit, api
└── domains/
    └── lending/   # schemas, break_types, rules, tools, prompts
datagen/       # synthetic data + break injector + ground truth
web/           # Next.js
docs/          # plan, ADRs, domain docs, evals
```

## Process

- Every task: own branch and PR. Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `ci:`, `refactor:`).
- Every significant decision: an ADR in `docs/adr/` (copy `docs/adr/0000-template.md`).
- Never ask for keys or passwords in chat. Check only whether a variable is set; never print values.
- Do not push, merge, tag, or change GitHub settings without asking the user.
