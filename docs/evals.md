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
| S1 | Break detection precision and recall, every break type | ≥ 0.98 | 1.000 (4 seeds) | yes |
| S2 | Share of simple breaks closed by rules | ≥ 0.90 | 1.000 (5 seeds) | yes |
| S3 | Rules claiming a medium or hard break | 0 | 0 (5 seeds) | yes |
| S4 | Medium breaks: workflow root cause accuracy | ≥ 0.80 | 1.000 (seed 42, flash-lite) | yes |
| S5 | Medium breaks: citation accuracy (amendment and section in force) | ≥ 0.80 | 0.943 exact set (seed 42, flash-lite) | yes |
| S6 | Hard breaks routed to `needs_investigation` | ≥ 0.90 | 1.000, all by the code gate (ADR 0012) | yes |
| S7 | LLM cost per break reaching the workflow | ≤ $0.01 | $0.000439 | yes |
| S8 | Reviewer goes from a break to approve/reject in the UI without a terminal | yes | yes (owner, `make demo`, 2026-10-07) | yes |

S1–S3 are engineering gates; S4–S7 decide the hypothesis; S8 decides whether the product is demonstrable.

## Primary metric: break closure cascade

Rules row from MVP M2, Workflow row from M3, Agent row from post-MVP P5. This is the central README table.

| Level | Share closed — simple | medium | hard | Accuracy | Cost / break | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|---|---|
| Rules | 1.000 (62/62) | 0.000 (0/70) | 0.000 (0/146) | cause 1.000, wrong side 1.000, proposal 1.000 (62 explained) | $0 | | seed 42, 30 days, 40 loans per batch, 278 labeled breaks | `afaf43b` | |
| Workflow | — | 1.000 (70/70) | 0.000 (146 → `needs_investigation`) | S4 1.000, S5 0.943 | $0.000439 | 5.97 / 26.60 | seed 42, gemini-3.5-flash-lite | `53bc5c4` |
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

## MVP M2 — rules

Targets: S2 (share of simple breaks closed by rules) ≥ 0.90 and S3 (rules claiming a medium or hard break) = 0, on seed 42 and seeds 7, 1234, 2026.

Command: `kredpare eval rules <dir> --as-of 2026-09-08 --markdown` (ingest, matching, and the rule level in a temporary database; exits non-zero if S2 < 0.90 or S3 > 0). Dataset: `kredpare-datagen --days 30`, window 2026-08-10 to 2026-09-08, 40 loans per batch. Commit `afaf43b`. Semantics: ADR 0010.

"Breaks" are ground-truth breaks expanded as `loan_ids × fields` (one per loan for missing, duplicate, and stale records). "Explained" means a rule explanation was stored. Accuracy is measured among explained breaks only; `-` means nothing was explained.

| Cause | Difficulty | Explained / breaks (seed 42 / 7 / 1234 / 2026) | Cause acc. | Wrong side acc. | Proposal acc. |
|---|---|---|---|---|---|
| `loan_not_confirmed` | simple | 3/3 · 3/3 · 3/3 · 3/3 | 1.000 | 1.000 | 1.000 |
| `loan_not_offered` | simple | 2/2 · 2/2 · 2/2 · 2/2 | 1.000 | 1.000 | 1.000 |
| `duplicate_row` | simple | 2/2 · 2/2 · 2/2 · 2/2 | 1.000 | 1.000 | 1.000 |
| `confirmation_overdue` | simple | 40/40 · 40/40 · 40/40 · 40/40 | 1.000 | 1.000 | 1.000 |
| `settlement_date_roll` | simple | 3/3 · 3/3 · 3/3 · 3/3 | 1.000 | 1.000 | 1.000 |
| `rounding_difference` | simple | 6/6 · 6/6 · 6/6 · 6/6 | 1.000 | 1.000 | 1.000 |
| `accrual_start_alternative` | simple | 6/6 · 6/6 · 6/6 · 6/6 | 1.000 | 1.000 | 1.000 |
| `accrued_interest_error` | medium | 0/8 · 0/8 · 0/8 · 0/8 | - | - | - |
| `price_grid_amendment` | medium | 0/62 · 0/66 · 0/78 · 0/68 | - | - | - |
| `combined_causes` | hard | 0/6 · 0/6 · 0/6 · 0/6 | - | - | - |
| `dealer_wide_adjustment` | hard | 0/6 · 0/12 · 0/8 · 0/16 | - | - | - |
| `unannounced_rule_change` | hard | 0/134 · 0/128 · 0/136 · 0/136 | - | - | - |

| Seed | Simple explained (S2) | Medium explained | Hard explained | S3 (medium + hard explained) |
|---|---|---|---|---|
| 42 | 62/62 = 1.000 | 0/70 | 0/146 | 0 |
| 7 | 62/62 = 1.000 | 0/74 | 0/146 | 0 |
| 1234 | 62/62 = 1.000 | 0/86 | 0/150 | 0 |
| 2026 | 62/62 = 1.000 | 0/76 | 0/158 | 0 |

Both targets are met on all four seeds. Notes:

- The simple support is the same on every seed because the injection plan fixes the number of loans per simple cause; only medium and hard supports vary with the seed.
- 1.000 shows the rules and the generator agree on cause semantics; the rules were written against the taxonomy, not tuned to any seed. It says nothing about messy real files.
- Rules never read agreements (ADR 0010). `combined_causes` and `accrued_interest_error` loans are left unexplained by design; that is what keeps S3 at 0.
- CI runs this eval on seed 42 and fails below S2 0.90 or above S3 0.
- Latency was not measured; rules run in memory over stored records.

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
| long context (no RAG) | — | — | 5.97 / 26.60 | $0.001353 / call | seed 42, gemini-3.5-flash-lite, citation accuracy 0.943 | `53bc5c4` |

## MVP M3 — workflow explainer

Run on both models; the model choice is an eval result.

| Model | Root cause accuracy | Citation correctness | `needs_investigation` rate on hard | Cost / break | Dataset | Commit |
|---|---|---|---|---|---|---|
| gemini-3.5-flash-lite | 1.000 | 0.943 (exact set; 0.986 expected-cited) | 1.000 | $0.000439 | kredpare-datagen --days 30, seed 42 (70 medium, 146 hard) | `53bc5c4` |
| gemini-3.5-flash | | | | | pending: run did not finish before this PR | |

## Post-MVP P5 — workflow vs agent on the hard set

| Approach | Root cause accuracy | Trajectory score | Cost / case | p50 / p95 | Dataset | Commit |
|---|---|---|---|---|---|---|
| workflow | | — | | | | |
| agent | | | | | | |

## Log

Append one line per recorded change: date, table, what changed, why.

- 2026-10-05 · MVP success criteria · targets S1–S8 fixed and section headings moved to the MVP and post-MVP plans · ADR 0008, issue #43.
- 2026-10-05 · MVP M1 break detection · first measurement, 1.000 on seeds 42, 7, 1234, 2026 · commit 1499a43.
- 2026-10-05 · MVP M2 rules · first measurement, S2 1.000 and S3 0 on seeds 42, 7, 1234, 2026; cascade Rules row filled · commit afaf43b · ADR 0010.

### MVP M3 notes (seed 42, gemini-3.5-flash-lite)

- 216 breaks reached the workflow: 70 called the LLM (all medium), 146 hard breaks were short-circuited by code because no clause-supported candidate reproduces the counterparty value. S6 = 1.000 is therefore a property of the code gate, not of the model.
- Total spend $0.0947 ($0.001353 per call); 0 invalid outputs, 2 retries, 0 unavailable.
- Wrong-side accuracy on medium: 1.000. Rule level unchanged: S2 1.000, S3 0.
- Precomputed candidates make root-cause selection easy (S4 1.000); citations are where the model errs (S5 0.943 exact set).
