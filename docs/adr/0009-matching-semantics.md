# 0009. Define what matching reports: per-file duplicates and delivery-aware missing records

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** MVP M1

## Context

Matching must turn records into typed breaks without deciding causes, and its output is scored against ground truth (S1). Three cases are ambiguous if matching only compares keys:

- A loan confirmed again in a different batch (`loan_not_offered`) puts the same loan id in two buyer files. That is not a duplicate row.
- A seller loan missing from the buyer's side means one thing if the buyer's file for that batch arrived without it (`loan_not_confirmed`), and another if the file has not arrived yet (`confirmation_overdue`, pending until it ages).
- A confirmed loan not yet boarded by the servicer is normal for a few days.

A separate problem: Polars infers a Decimal column's scale from the first 100 rows and silently rounds later rows to it (measured: `1.25` became `1.2`).

## Decision

- `duplicate` means the same record id twice **in one file**. For comparisons, the first row per match key is used, so a duplicate never doubles other breaks.
- A `MatchDeclaration` may name `delivery_fields` (lending: `counterparty_id`, `batch_id`). A left record missing on the right is `missing_record` only if the right side delivered that group. Otherwise it is pending, and it becomes `stale_pending` once `as_of` is more than N business days after `age_from` (lending: the cut-off date for confirmations, the settlement date for boarding; N = 5; US federal holiday calendar supplied by the domain).
- A record present only on the right is always `missing_record` on the left.
- DuckDB does the set work over VARCHAR columns; amounts are compared in Python as `Decimal`, dates as ISO text. `delta` is right minus left.
- Canonical frames are built with `canonical_frame` (Polars `Object` columns), never with type inference.
- Breaks have a natural key per as-of date, so rerunning matching is idempotent.

## Alternatives considered

| Option | Why not |
|---|---|
| Duplicate = same key twice on one side across files | Labels every `loan_not_offered` as a duplicate too. |
| Every one-sided record is `missing_record` | Cannot tell a dropped loan from a file not yet received; unboarded loans would be false breaks for days. |
| Compare amounts in DuckDB as DECIMAL | Works, but a fixed DECIMAL scale is one more place where rounding could hide; Python `Decimal` compares exactly what was stored. |

## Consequences

- **Positive:** precision and recall are 1.000 on four seeds; the distinction between missing and pending matches the break taxonomy.
- **Negative / cost:** matching loads all records into memory each run; fine for daily files of thousands of rows, revisit for larger volumes. A corrected re-sent file (new sha256, same batch) is ingested as an additional file; replacement semantics are out of MVP scope.
- **Follow-up:** P1 (production ingest) decides how a re-sent file supersedes the previous one.
