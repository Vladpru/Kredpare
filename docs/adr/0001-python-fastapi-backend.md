# 0001. Use Python and FastAPI for the backend

- **Status:** Accepted
- **Date:** 2026-10-02
- **Iteration:** −1

## Context

The backend combines data processing (CSV normalization, validation, matching), document parsing (agreements), LLM orchestration with human-in-the-loop pauses, and evals. The author's strongest stack is TypeScript (NestJS, Next.js); Python is new. The project targets AI engineer roles, where Python is the expected backend language.

The libraries the plan depends on are Python-first or Python-only: LangGraph (persistence, `interrupt`, `Send`, Store), Pydantic, Polars, Pandera, DuckDB, Docling, Presidio, Hypothesis, LangSmith evals.

## Decision

Write the backend in Python 3.12 with FastAPI, managed by `uv`. Pydantic models are the single source for API schemas; the frontend gets TypeScript types generated from OpenAPI. The frontend stays in Next.js (TypeScript).

## Alternatives considered

| Option | Why not |
|---|---|
| NestJS + LangGraph.js | LangGraph.js lags the Python version; no Docling, Presidio, Pandera, or Hypothesis equivalents of the same maturity. |
| Python with Django | Heavier than needed; async and OpenAPI-first design are more natural in FastAPI. |
| Mixed: TS API + Python workers | Two backend languages and a duplicated domain model for a solo project. |

## Consequences

- **Positive:** direct access to the AI and data ecosystem; matches the target role.
- **Negative / cost:** learning curve. The plan's risk section applies: if behind schedule, cut iteration 9 scope, not evals or the cascade.
- **Follow-up:** strict typing (pyright) and ruff from Iteration 0 to compensate for language inexperience.
