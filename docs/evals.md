# Evals

Every AI component gets a **baseline** here before it is optimized. After a baseline is recorded, CI must not let the metric regress.

Rules for every table:

- Record real numbers only. An empty cell means "not measured yet", never an estimate.
- Each row states the **dataset** (name, size, datagen seed) and the **commit** it was measured on.
- Cost is USD per item, from LangSmith traces. Latency is p50 / p95 in seconds.
- Targets come from `MVP_PLAN.md` (success criteria) and, after the MVP, `POST_MVP_PLAN.md`. A missed target is recorded as-is, with a note.

## MVP success criteria

Fixed on 2026-10-05, before any measurement (`docs/MVP_PLAN.md`, issue #43). Targets are not edited after M1 starts. "Measured" is filled in M4 for the verdict.

| # | Criterion | Target | Measured | Met |
|---|---|---|---|---|
| S1 | Break detection precision and recall, every break type | ≥ 0.98 | | |
| S2 | Share of simple breaks closed by rules | ≥ 0.90 | | |
| S3 | Rules claiming a medium or hard break | 0 | | |
| S4 | Medium breaks: workflow root cause accuracy | ≥ 0.80 | | |
| S5 | Medium breaks: citation accuracy (amendment and section in force) | ≥ 0.80 | | |
| S6 | Hard breaks routed to `needs_investigation` | ≥ 0.90 | | |
| S7 | LLM cost per break reaching the workflow | ≤ $0.01 | | |
| S8 | Reviewer goes from a break to approve/reject in the UI without a terminal | yes | | |

S1–S3 are engineering gates; S4–S7 decide the hypothesis; S8 decides whether the product is demonstrable.

## Primary metric: break closure cascade

Rules row from MVP M2, Workflow row from M3, Agent row from post-MVP P5. This is the central README table.

| Level | Share closed — simple | medium | hard | Accuracy | Cost / break | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|---|---|
| Rules | | | | | | | | |
| Workflow | | | | | | | | |
| Agent | | | | | | | | |
| Escalated | | | | — | — | — | | |

## MVP M1 — break detection (deterministic)

Target (S1): precision and recall ≥ 0.98 per type, on seed 42 and 3 other seeds.

Command: `kredpare eval matching <dir> --as-of 2026-09-08` (ingest and matching in a temporary database). Dataset: `kredpare-datagen --days 30`, window 2026-08-10 to 2026-09-08, 40 loans per batch. Commit `1499a43`.

| Break type | Precision | Recall | Support (seed 42 / 7 / 1234 / 2026) |
|---|---|---|---|
| `missing_record` | 1.000 | 1.000 | 5 / 5 / 5 / 5 |
| `duplicate` | 1.000 | 1.000 | 2 / 2 / 2 / 2 |
| `amount_mismatch` | 1.000 | 1.000 | 228 / 232 / 248 / 246 |
| `date_mismatch` | 1.000 | 1.000 | 3 / 3 / 3 / 3 |
| `stale_pending` | 1.000 | 1.000 | 40 / 40 / 40 / 40 |

Precision and recall are identical on all four seeds. Note: matching is deterministic and the data is synthetic, so 1.000 shows the engine and the generator agree on break semantics (ADR 0009); it says nothing yet about messy real files. CI runs this eval on seed 42 and fails below 0.98.

## Post-MVP P2 — LLM schema mapping

| Variant | Field accuracy | Transform accuracy | Cost / file | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|
| baseline | | | | | | |

## Post-MVP P3 — retrieval over agreements

The long context row is measured in MVP M3.

| Variant | recall@5 | MRR | p50 / p95 | Cost / query | Dataset | Commit |
|---|---|---|---|---|---|---|
| vector only | | | | | | |
| hybrid (RRF) | | | | | | |
| hybrid + rerank | | | | | | |
| long context (no RAG) | | | | | | |

## MVP M3 — workflow explainer

Run on both models; the model choice is an eval result.

| Model | Root cause accuracy | Citation correctness | `needs_investigation` rate on hard | Cost / break | Dataset | Commit |
|---|---|---|---|---|---|---|
| Haiku | | | | | | |
| Sonnet | | | | | | |

## Post-MVP P5 — workflow vs agent on the hard set

| Approach | Root cause accuracy | Trajectory score | Cost / case | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|
| workflow | | — | | | | |
| agent | | | | | | |

## Log

Append one line per recorded change: date, table, what changed, why.

- 2026-10-05 · MVP success criteria · targets S1–S8 fixed and section headings moved to the MVP and post-MVP plans · ADR 0008, issue #43.
- 2026-10-05 · MVP M1 break detection · first measurement, 1.000 on seeds 42, 7, 1234, 2026 · commit 1499a43.
