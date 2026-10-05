# 0010. Define the rule level: conflicts go to the workflow, no agreements, convention inferred from the seller

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** MVP M2

## Context

The rule level is the first step of the cascade (ADR 0005). It must close simple breaks with an exact, reproducible explanation and must never claim a medium or hard break (S3 = 0), because a wrong rule explanation is worse than a workflow call. Four questions were open:

- Two rules may both explain one break. Picking one is a guess.
- Amount rules recompute accrued interest, which needs a day-count convention. The convention comes from the agreement and can change by amendment, but reading agreements is the workflow's job (M3).
- `combined_causes` (old convention plus truncation) and `accrued_interest_error` (an amendment moved the convention) must not be claimed. The datagen injector guarantees combined loans are not reproduced by truncation alone under the convention in force (`leaves_residual`).
- Explanations must be stored so a reviewer can see them and later levels can build on them.

## Decision

- **A break is explained only when exactly one rule explains it.** The runner asks the rules that handle the break type, in the order of `DomainSpec.rules`. One explanation: status `explained`, explanation stored. None: status `pending_workflow`. More than one: status `pending_workflow`, nothing stored, the audit event lists `conflicting_rules`. Rerunning only touches `open` breaks, so it is idempotent. Every status change writes an `audit_events` row (`rule:<name>` for an explanation, `cascade` for a hand-off).
- **Rules never read agreements.** A rule sees the break, its records, and a read-only parameterized record and break query (`RuleContext`, no free SQL).
- **The day-count convention is inferred from the seller record.** Candidate conventions are those for which half-up accrual from the funding date reproduces the seller's `accrued_interest` exactly. `rounding_difference` and `accrual_start_alternative` explain only if a candidate also reproduces the counterparty value exactly, for both `accrued_interest` and `purchase_price` breaks. If no candidate reproduces the seller value, or none reproduces the counterparty value, the rule stays silent. No tolerance is used to explain.
- **Explanations live in `explanations`**: break, level (`rule`), rule, cause, wrong side (`seller`, `counterparty`, or null for a reminder), proposal kind (`correction` or `email`), and JSONB evidence with decimals as strings and dates as ISO strings. One per break and level. An explanation is a proposal; nothing is applied without human approval.
- Wrong side and proposal follow `docs/domain/break-taxonomy.md`. `settlement_date_roll` blames the side that did not roll; `duplicate_row` blames the file owner; `confirmation_overdue` blames nobody and proposes a reminder email.

## Alternatives considered

| Option | Why not |
|---|---|
| On conflict, pick the first or the most specific rule | A guess presented as an explanation; hurts S3. A conflict is a signal the rules overlap and is better resolved by the workflow. |
| Rules read the agreement's day-count and pricing terms | Duplicates the workflow, puts document reading in code, and still fails on amendments, which is exactly what the medium level is for. |
| Pass the convention to rules from a per-counterparty config | A second source of truth that the amendment case would contradict. |
| Try all conventions against the counterparty value only | Would claim `accrued_interest_error` whenever the old convention happens to reproduce the counterparty value. |
| Store the explanation as a column on `breaks` | Later levels need one explanation per level and a history. |

## Consequences

- **Positive:** rule explanations are exact and conservative; S3 stays at 0 by construction; every decision is audited; the workflow receives everything the rules could not close.
- **Negative / cost:** a seller value that is itself wrong (amendment ignored by the seller) is never explained by rules, even when a rule would have been right by luck. Two conventions that give the same seller value are both candidates; evidence lists all candidates and the first that reproduces the counterparty value.
- **Follow-up:** M3 reads the status `pending_workflow`. Revisit conflict handling if real data shows frequent overlap between rules. Revisit convention inference if a seller computes with a convention no candidate set covers.
