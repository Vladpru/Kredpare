# Canonical schema

Status: **approved** 2026-10-05. All values are synthetic. Implemented in Iteration 1 (Pydantic for records, Pandera for file-level validation).

Every counterparty file is mapped into one of these schemas. Matching, rules, and tools only ever see canonical records, never raw columns.

## Conventions

| Kind | Python type | Canonical form | Example |
|---|---|---|---|
| Money | `Decimal` | USD, exactly 2 decimal places, never `float` | `Decimal("20365.69")` |
| Rate | `Decimal` | Annual rate as a fraction, 6 decimal places | note rate 9.99% → `Decimal("0.099900")` |
| Price | `Decimal` | Fraction of UPB, 6 decimal places | 101.50% → `Decimal("1.015000")` |
| Date | `datetime.date` | No time, no time zone | `2026-09-14` |
| Id | `str` | Trimmed, case preserved | `"L-004512"` |

- Currency is USD only in v1. There is no `currency` field.
- Transforms (`parse_usd`, `cents_to_decimal`, `parse_date_mdy`, …) convert source values into this form. Rounding never happens inside a transform: a source value with more than 2 decimals is a validation error, not silently rounded.

## Core: base canonical record (`core/`)

Generic. Contains no lending words.

| Field | Type | Meaning |
|---|---|---|
| `record_id` | `str` | Business key of the record within the counterparty (for lending: the loan id). |
| `counterparty_id` | `str` | Owner of the file. |
| `batch_id` | `str` | Group the record is reconciled in. Taken from a column, or set at ingest from upload metadata when the file has no such column. |
| `file_id` | `UUID` | Source file (immutable, sha256 in S3). |
| `row_number` | `int` | Row in the source file, for citations and duplicates. |
| `schema_name` | `str` | Domain schema the record follows, for example `FundedLoan`. |
| `match_status` | enum | `unmatched` → `matched` or `in_break`. Set by matching, never by the domain. |

The domain declares which of its fields are the **match key**, which are **compared money fields**, and which are **compared date fields**. Core matching reads that declaration from `DomainSpec`; it does not hard-code field names.

## Lending schemas (`domains/lending/schemas/`)

### `FundedLoan` — seller file, one row per loan offered in a batch

| Field | Type | Rules |
|---|---|---|
| `loan_id` | `str` | → `record_id`. Format `L-` + 6 digits. |
| `batch_id` | `str` | `{counterparty_id}-{settlement_date}` |
| `dealer_id` | `str` | Format `D-` + 4 digits. |
| `credit_tier` | enum `A`/`B`/`C`/`D` | Selects the price in the pricing grid. |
| `funding_date` | date | ≤ `cut_off_date` |
| `cut_off_date` | date | ≤ `settlement_date` |
| `settlement_date` | date | Business day expected by the seller. |
| `funded_amount` | money | > 0 |
| `upb` | money | > 0, ≤ `funded_amount` |
| `note_rate` | rate | 0 < rate ≤ 0.36 |
| `term_months` | int | 12 ≤ term ≤ 84 |
| `price_pct` | price | Seller's expected price from the grid in force. |
| `accrued_interest` | money | Seller's calculation. ≥ 0 |
| `purchase_price` | money | Must equal `round_half_up(upb × price_pct, 2) + accrued_interest` (the seller file is internally consistent). |

### `PurchaseConfirmation` — counterparty file, one row per loan bought

| Field | Type | Rules |
|---|---|---|
| `loan_id` | `str` | → `record_id` |
| `batch_id` | `str` | Often missing in source; set from upload metadata. |
| `settlement_date` | date | |
| `upb` | money | > 0 |
| `price_pct` | price | |
| `accrued_interest` | money | ≥ 0 |
| `purchase_price` | money | Not re-validated against the formula: the counterparty may compute it differently, and that difference is a break, not a validation error. |

No `dealer_id` and no `credit_tier`: counterparties do not send them. Agent queries join to `FundedLoan` by `loan_id`.

### `ServicerOnboarding` — servicer file, one row per boarded loan

| Field | Type | Rules |
|---|---|---|
| `loan_id` | `str` | → `record_id` |
| `boarded_date` | date | ≥ `settlement_date` of the loan |
| `upb` | money | > 0 |
| `next_payment_due_date` | date | > `boarded_date` |

## Matching declarations (lending)

| Pair | Match key | Money fields | Date fields |
|---|---|---|---|
| `FundedLoan` ↔ `PurchaseConfirmation` | `counterparty_id`, `batch_id`, `loan_id` | `upb`, `price_pct`, `accrued_interest`, `purchase_price` | `settlement_date` |
| `PurchaseConfirmation` ↔ `ServicerOnboarding` | `loan_id` | `upb` | — (boarding delay is `stale_pending`) |

`price_pct` is not money, but it is compared exactly like a money field. It is listed here so that `price_grid_amendment` produces a break on the price itself, not only on `purchase_price`.

## Simplifying assumption for v1

Loans are sold **before the first borrower payment**. So `upb = funded_amount` and accrued interest always starts at `funding_date` (unless an agreement or a break says otherwise). This removes paid-to-date tracking from v1. The `upb` field is still kept separate so the assumption can be lifted later without a schema change.

## Validation failures

A row that fails these rules is stored with its errors and shown to the user. It is never dropped silently and never becomes a break: breaks are only produced from valid records.

## Decisions

- Loans are sold before the first borrower payment in v1. Approved 2026-10-02.
- `FundedLoan` carries the seller's expected `price_pct`, `accrued_interest`, and `purchase_price`. Kredpare does not compute the seller side from the agreement. Reason: real seller tapes look like this, and seller-side errors must be possible. Approved 2026-10-02.
