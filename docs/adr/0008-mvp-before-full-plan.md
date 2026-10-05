# 0008. Build an MVP that tests the core hypothesis before the full plan

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** after 1

## Context

The original plan (`IMPLEMENTATION_PLAN.md`) reaches a working break explanation only in Iteration 5 (week 8) and a usable product in Iteration 8 (week 11). Iterations 2–4 build production ingest, LLM mapping, and RAG before anything shows whether the product idea works at all. Iteration 1 already provides synthetic files with labeled ground truth, which is enough to measure the core idea directly.

## Decision

Before continuing with the full plan, build an MVP (`MVP_PLAN.md`) that tests one hypothesis: rules plus one LLM call that reads the agreement can explain most breaks correctly, with a citation, at low cost, and route the rest to a human honestly. The MVP keeps every non-negotiable rule (`Decimal`, only code computes money, the cascade, audit, human approval, evals first). It replaces S3/Celery ingest with a CLI, LLM mapping with hand-written mappings, RAG with the whole agreement in the prompt, and the case lifecycle with recorded approve/reject decisions. Success criteria are fixed before measuring. The remaining work is reordered into `POST_MVP_PLAN.md` and starts only after a written verdict.

## Alternatives considered

| Option | Why not |
|---|---|
| Continue the full plan in order | About 6 more weeks before the first evidence that explanations work. |
| MVP without evals, judged by demo only | Cannot tell a good idea from good-looking output; evals already exist cheaply thanks to the ground truth. |
| MVP with RAG instead of long context | Three short agreements fit in a prompt; RAG answers a scaling question, not the core one. Its baseline row comes from the MVP. |

## Consequences

- **Positive:** a measured go/no-go after about 6 weeks. Every MVP component is reused by the post-MVP phases (ingest becomes a Celery task, the workflow becomes a LangGraph node, the decision endpoint becomes HITL #2).
- **Negative / cost:** some rework when ingest moves behind the API and the workflow moves into LangGraph. Long context may look better than it would on real, longer agreements.
- **Follow-up:** M4 writes ADR 0009 with the verdict. GitHub milestones for Iterations 2–10 should be replaced by MVP M1–M4 and post-MVP P1–P8 milestones.
