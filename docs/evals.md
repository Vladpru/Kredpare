# Evals

Every AI component gets a **baseline** here before it is optimized. After a baseline is recorded, CI must not let the metric regress.

Rules for every table:

- Record real numbers only. An empty cell means "not measured yet", never an estimate.
- Each row states the **dataset** (name, size, datagen seed) and the **commit** it was measured on.
- Cost is USD per item, from LangSmith traces. Latency is p50 / p95 in seconds.
- Targets come from `IMPLEMENTATION_PLAN.md`. A missed target is recorded as-is, with a note.

## Primary metric: break closure cascade

Updated in Iterations 5 and 7. This is the central README table.

| Level | Share closed — simple | medium | hard | Accuracy | Cost / break | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|---|---|
| Rules | | | | | | | | |
| Workflow | | | | | | | | |
| Agent | | | | | | | | |
| Escalated | | | | — | — | — | | |

## Iteration 2 — break detection (deterministic)

Target: precision and recall ≥ 0.98 per type.

| Break type | Precision | Recall | Support | Dataset | Commit |
|---|---|---|---|---|---|
| `missing_record` | | | | | |
| `duplicate` | | | | | |
| `amount_mismatch` | | | | | |
| `date_mismatch` | | | | | |
| `stale_pending` | | | | | |

## Iteration 3 — LLM schema mapping

| Variant | Field accuracy | Transform accuracy | Cost / file | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|
| baseline | | | | | | |

## Iteration 4 — retrieval over agreements

| Variant | recall@5 | MRR | p50 / p95 | Cost / query | Dataset | Commit |
|---|---|---|---|---|---|---|
| vector only | | | | | | |
| hybrid (RRF) | | | | | | |
| hybrid + rerank | | | | | | |
| long context (no RAG) | | | | | | |

## Iteration 5 — workflow explainer

| Variant | Root cause accuracy | Citation correctness | `needs_investigation` rate on hard | Cost / break | Dataset | Commit |
|---|---|---|---|---|---|---|
| baseline | | | | | | |

## Iteration 7 — workflow vs agent on the hard set

| Approach | Root cause accuracy | Trajectory score | Cost / case | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|
| workflow | | — | | | | |
| agent | | | | | | |

## Log

Append one line per recorded change: date, table, what changed, why.
