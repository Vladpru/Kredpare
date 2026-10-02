# 0004. Split the code into a domain-agnostic core and pluggable domains

- **Status:** Accepted
- **Date:** 2026-10-02
- **Iteration:** −1

## Context

v1 reconciles lending files (forward flow loan sales). After v1 a payments domain (settlement ↔ bank statement) is planned to prove the engine is generic. If lending concepts leak into ingestion, matching, rules, RAG, or case handling, the second domain becomes a rewrite.

## Decision

Two packages under `backend/src/kredpare/`:

- `core/` — ingestion, mapping, matching, rule runner, RAG, case lifecycle, audit, API. Uses only generic terms: `counterparty`, `agreement`, `record`.
- `domains/<name>/` — schemas, break types, rules, tools, and prompts. A domain registers them with core through a `DomainSpec` interface.

`core/` must never import `domains/`. An `import-linter` contract enforces this in CI from Iteration 0.

## Alternatives considered

| Option | Why not |
|---|---|
| One package, refactor when payments arrives | The boundary is exactly what v3 is meant to prove; retrofitting it is the expensive path. |
| Plugin system with entry points | Speculative for two domains in one repo. |
| Boundary by convention only | Violations slip in silently; a CI check is cheap. |

## Consequences

- **Positive:** v3 success is measurable: a payments PR with a minimal diff in `core/`.
- **Negative / cost:** some indirection (registration, declared match keys) earlier than a single-domain app needs.
- **Follow-up:** code moves into `core/` only when it is actually needed by core, never "just in case".
