# 0002. Use Celery with Redis for background jobs and schedules

- **Status:** Accepted
- **Date:** 2026-10-02
- **Iteration:** −1

## Context

File ingestion, agreement indexing, and break investigation take seconds to minutes and must not run inside HTTP requests. Reconciliation runs daily per counterparty and evals run nightly, so a scheduler is needed. Long human-in-the-loop pauses (days) are a separate concern: LangGraph persists them with `PostgresSaver`, so the job system does not need to hold state across days.

## Decision

Use Celery workers with Redis as broker and result backend, and Celery Beat for schedules. Tasks: `ingest_file`, `ingest_agreement`, `investigate_break`, the daily run, and nightly evals. Tasks are idempotent and keyed by ids (file sha256, case id) so retries are safe.

## Alternatives considered

| Option | Why not |
|---|---|
| FastAPI `BackgroundTasks` | Runs in the API process: no retries, no scheduling, lost on restart. |
| RQ / Dramatiq / Arq | Viable and lighter, but less widely recognized and weaker built-in scheduling. |
| Temporal | Durable workflows would overlap with LangGraph persistence; heavy to operate for a solo project. |

## Consequences

- **Positive:** well-known stack; retries, routing, and Beat schedules out of the box. Redis is reused for rate limits and the semantic cache.
- **Negative / cost:** Celery is synchronous by default; async code needs care inside tasks. One more process to deploy (worker + beat).
- **Follow-up:** revisit if task orchestration starts duplicating what LangGraph already persists.
