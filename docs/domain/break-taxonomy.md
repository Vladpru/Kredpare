# Break taxonomy (lending)

Status: **draft for review**. All examples are synthetic.

## Two axes: break type and root cause

A break has two independent labels:

- **Break type** — the *symptom* the matching engine detects. Deterministic, no AI. Evaluated with precision/recall per type (Iteration 2).
- **Root cause** — *why* the symptom exists. This is what the cascade explains, and what `ground_truth.jsonl` records for every injected break together with its difficulty level.

One break type can have many root causes. For example, `amount_mismatch` on `accrued_interest` can come from a rounding difference (rule), an amendment (workflow), or an unannounced counterparty change (agent).

## Reconciled file pairs

| Pair | Match key | Compared fields |
|---|---|---|
| `FundedLoan` ↔ `PurchaseConfirmation` | `counterparty_id`, `loan_id`, `batch_id` | `upb`, `price_pct`, `accrued_interest`, `purchase_price`, `settlement_date` |
| `PurchaseConfirmation` ↔ `ServicerOnboarding` | `loan_id` | `upb`, existence, boarding within N days |

Field names are defined in `canonical-schema.md`.

## Break types (detected by matching)

| Type | Detected when | Tolerance |
|---|---|---|
| `missing_record` | A record exists on one side only. Carries `missing_side`. | — |
| `duplicate` | The same match key appears more than once in one file. | — |
| `amount_mismatch` | A compared money field differs. Carries `field`, both values, and `delta`. | exact (`0.00`); rounding is explained by a rule, not hidden by tolerance |
| `date_mismatch` | A compared date field differs. Carries `field` and both values. | exact |
| `stale_pending` | A seller record has no counterparty confirmation (or a confirmed loan is not boarded) more than N business days after the cut-off date. | N per counterparty, default 5 business days |

Matching emits one break per (record, field). It never decides the cause.

**Out of scope for v1:** differences in non-money attributes such as `note_rate` or `dealer_id`. Matching does not compare them.

## Root causes (injected by datagen, explained by the cascade)

"Who is wrong" decides the proposal: if the **seller** is wrong, the proposal is a **correction**; if the **counterparty** is wrong, it is an **email** to the counterparty.

### Simple — closed by a rule (cascade level `rule`)

| Cause | Symptom | What happened | Who is wrong | Rule explains it by |
|---|---|---|---|---|
| `loan_not_confirmed` | `missing_record` (counterparty side) | Counterparty dropped a loan from its confirmation. | counterparty | Loan is in the seller file and absent from the confirmation for the same batch. |
| `loan_not_offered` | `missing_record` (seller side) | Counterparty confirmed a loan that was not in this batch (it belongs to another batch). | counterparty | Loan id exists in a different batch of the seller. |
| `duplicate_row` | `duplicate` | Same loan appears twice in a file. | file owner | Rows identical except row number. |
| `confirmation_overdue` | `stale_pending` | Counterparty has not confirmed the loan yet. | — (reminder) | Age past N business days, no other break on the loan. |
| `settlement_date_roll` | `date_mismatch` on `settlement_date` | Settlement date fell on a weekend or US bank holiday; one side rolled it to the next business day. | the side that did not roll | Dates differ by exactly the roll to the next business day. |
| `rounding_difference` | `amount_mismatch`, `|delta| ≤ 0.01` per loan | Counterparty truncates to cents instead of rounding half-up. | counterparty | Recomputing with truncation reproduces the counterparty value exactly. |
| `accrual_start_alternative` | `amount_mismatch` on `accrued_interest` | Counterparty accrues from the cut-off date instead of the funding date. | counterparty | Recomputing from the cut-off date reproduces the counterparty value exactly. |

### Medium — needs the agreement (cascade level `workflow`)

| Cause | Symptom | What happened | Who is wrong | Why a rule is not enough |
|---|---|---|---|---|
| `accrued_interest_error` (amendment) | `amount_mismatch` on `accrued_interest` (and `purchase_price`) | An amendment changed the day-count convention (for example 30/360 → Actual/365) from its effective date. One side still uses the old convention for batches after that date. | depends on which side ignored the amendment | The correct convention depends on which agreement version is in force on the settlement date. The explanation must cite the amendment section. |
| `price_grid_amendment` | `amount_mismatch` on `price_pct` and `purchase_price`; `accrued_interest` matches | An amendment changed the price for one credit tier from its effective date (for example, Tier B 101.50% → 101.00%). One side still uses the old price. On a $20,000.00 UPB loan the delta is $100.00. | depends on which side ignored the amendment | The correct price depends on which pricing grid is in force on the settlement date. The explanation must cite the amended pricing grid section. |

### Hard — needs the agent (cascade level `agent`)

| Cause | Symptom | What happened | Why the workflow is not enough |
|---|---|---|---|
| `dealer_wide_adjustment` | `amount_mismatch` on `purchase_price` for every loan of one dealer in a batch | Counterparty applied a lower price tier to one dealer (for example, the dealer was put on a watch list) without telling the seller. | No single loan explains it. The pattern appears only when querying all loans of the batch grouped by dealer. |
| `combined_causes` | `amount_mismatch` that no single rule or clause reproduces | Two causes on the same loan, for example amendment day-count **and** truncation, or alternative accrual start **and** a settlement date roll. | Each cause alone leaves a residual delta. The agent must decompose the delta with tool calls until the residual is zero. |
| `unannounced_rule_change` | `amount_mismatch` on `accrued_interest` from one date onward, across batches | Counterparty changed its calculation (for example, excludes the settlement day) without an amendment. The agreement still says the old rule. | No clause supports the counterparty value. The agent must find the change date from history, cite the clause being violated, and propose an email. |

Hard breaks must pass the plan's test: **you cannot explain them without querying other records.**

## Cascade outcome per difficulty (expected)

| Difficulty | Expected level | Correct outcome |
|---|---|---|
| simple | `rule` | `explained`, no LLM call |
| medium | `workflow` | `explained` with citation to the amendment in force |
| hard | `agent` (from Iteration 7) | Before Iteration 7: `needs_investigation`, never an invented explanation |
| any, unexplainable | `escalated` | Human queue |

## Ground truth record (draft)

One JSON line per injected break:

```json
{"break_id": "gt-000123", "counterparty_id": "cp-a", "batch_id": "2026-09-14", "loan_ids": ["L-004512"],
 "break_type": "amount_mismatch", "field": "accrued_interest", "cause": "accrued_interest_error",
 "difficulty": "medium", "wrong_side": "counterparty", "expected_level": "workflow",
 "expected_citation": "amendment-1 §4.2", "expected_proposal": "email"}
```

Hard causes list all affected `loan_ids` in one ground truth record.

## Decisions

- Two medium causes instead of the plan's one: `accrued_interest_error` and `price_grid_amendment`. Reason: with one cause, workflow evals would measure one memorized pattern, not agreement reading. Approved 2026-10-02.
- Non-money attribute differences are out of scope for v1.
- `stale_pending` default: 5 business days.
