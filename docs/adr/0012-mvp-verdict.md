# 0012. Continue with the post-MVP plan, with changes to evaluation

- **Status:** Proposed. It becomes Accepted when the reviewer checks S8 and the user confirms the decision.
- **Date:** 2026-10-07
- **Iteration:** MVP M4

## Context

The MVP ([ADR 0008](0008-mvp-before-full-plan.md)) tests one hypothesis: rules plus one LLM call that reads the agreement can explain most breaks correctly, with a citation, at low cost, and route the rest to a human honestly. Targets were fixed on 2026-10-05, before any measurement (`MVP_PLAN.md`), and were not changed afterwards. `MVP_PLAN.md` names this file `0009-mvp-verdict.md`, but 0009 was taken by the matching semantics ADR, so this ADR uses the next free number as the plan allows.

Dataset: `kredpare-datagen --days 30`, window 2026-08-10 to 2026-09-08, 40 loans per batch, `--as-of 2026-09-08`. Numbers come from `docs/evals.md`.

| # | Criterion | Target | Measured | Met |
|---|---|---|---|---|
| S1 | Break detection precision and recall, every type | ≥ 0.98 | 1.000 / 1.000 for all 5 types, seeds 42, 7, 1234, 2026 | yes |
| S2 | Simple breaks closed by rules | ≥ 0.90 | 1.000 on seeds 42, 7, 1234, 2026 and held-out 99 | yes |
| S3 | Rules claiming a medium or hard break | 0 | 0 on the same 5 seeds | yes |
| S4 | Medium: workflow root cause accuracy | ≥ 0.80 | 1.000 (70 breaks, seed 42, `gemini-3.5-flash-lite`) | yes |
| S5 | Medium: citation accuracy | ≥ 0.80 | 0.943 exact citation set, 0.986 expected citation present | yes |
| S6 | Hard routed to `needs_investigation` | ≥ 0.90 | 1.000 (146 breaks) | yes, see caveat 1 |
| S7 | LLM cost per break reaching the workflow | ≤ $0.01 | $0.000439 (216 breaks, 70 LLM calls, $0.095 total) | yes |
| S8 | Reviewer goes from a break to approve/reject in the UI | yes | Not checked yet: the reviewer must run `make demo` and confirm | pending |

## What worked

- **The cascade split the work as designed.** Rules closed every simple break and claimed nothing else. The workflow explained every medium break with the right cause and side. Hard breaks never received an invented explanation.
- **"Code computes, LLM chooses and cites" held.** Every amount comes from `pricing.py`. The LLM picked from precomputed candidates and returned 0 invalid outputs in 70 calls. A code gate checks the cited candidate, the citation and the confidence before anything counts as explained.
- **Cost is about 23 times under target**, because 146 of the 216 workflow breaks never reach the LLM.
- **Conservative defaults protected S3:** two conflicting rules leave the break unexplained, and the day-count convention is inferred from the seller record rather than from the agreements.
- **Audit and human approval:** every status change, LLM call and reviewer decision writes an `audit_events` row, and decisions apply nothing.

## What failed or is not proven

1. **S6 measures the code gate, not the model.** All 146 hard breaks were short-circuited because no clause-supported candidate reproduces the counterparty value, so the model never saw a hard break. The hypothesis "the LLM routes the rest honestly" is untested. A hard break that *does* have a plausible clause-supported candidate would reach the model, and we have no such case.
2. **Synthetic data agrees with itself.** S1–S4 at 1.000 show that the engine, the rules and the generator share one set of semantics. They say nothing about messy real files: unknown headers, partial re-sends, free-text fields.
3. **Precomputed candidates make cause selection easy.** That is the intended design (`MVP_PLAN.md` risks). The real error mode is citations: 0.943 exact.
4. **Long context hides retrieval.** Three short agreements per buyer fit in one prompt. That does not scale to real agreements of 50 or more pages.
5. **The model comparison is incomplete.** Only `gemini-3.5-flash-lite` was measured. The `gemini-3.5-flash` run did not finish in time, so the "model choice is an eval result" rule is only half done.
6. **Latency** is p50 6.0 s and p95 26.6 s on the free tier. That is acceptable for a daily batch, but makes `make demo` slow (about 10 minutes when a key is set).
7. **Coverage gap:** a `stale_pending` break on servicer boarding has no rule. None occurs in the current data.

## Decision

Continue with `POST_MVP_PLAN.md`, with changes. The hypothesis holds on synthetic data, but the evidence for S6 and S5 is weaker than the numbers suggest. Before starting the agent level (P5), the evaluation must be hardened:

- **Adversarial hard set:** add hard breaks whose counterparty value *is* reproduced by a clause-supported candidate under the wrong agreement version or for the wrong reason. Measure S6 on breaks that reach the LLM, separately from the code gate.
- **Model comparison:** finish the `gemini-3.5-flash` run and add a second seed, then pick the default model from the numbers.
- **Citation errors:** sample and categorize the S5 misses before any prompt work. Do not tune on seed 42.
- **Realistic inputs:** keep P1 (production ingest) and P2 (LLM mapping) ahead of the agent level, so the S1–S3 gates face messy files.
- **Retrieval:** P3 replaces long context with retrieval, measured against the "long context" row recorded in M3.

## Alternatives considered

| Option | Why not |
|---|---|
| Continue with the post-MVP plan as is | S6 = 1.000 would hide that the model was never tested on hard breaks; the agent level (P5) would be built on an unmeasured routing claim. |
| Stop | Every target met, and costs are far under budget. The weak spots are gaps in the evaluation, not evidence against the hypothesis. |

## Consequences

- **Positive:** the cascade, audit and approval design is validated end to end. The review UI and `make demo` give a working demonstration.
- **Negative / cost:** about one extra iteration of eval work (adversarial set, model comparison, citation analysis) before P5.
- **Follow-up:**
  - The reviewer checks S8 and records it in `docs/evals.md`. This ADR then becomes Accepted.
  - Add the eval-hardening items to `POST_MVP_PLAN.md`.
  - Revisit this decision if the adversarial hard set drops S6 below 0.90, or if the second model or seed drops S4 or S5 below 0.80.
