# 0006. Keep row rules in Pydantic and file shape in Pandera

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** 1

## Context

The plan asks for Pydantic records and Pandera file-level validation. Most canonical rules are per row and cross-field (dates in order, `upb ≤ funded_amount`, the `purchase_price` formula). Writing each rule twice, once as a Pandera check and once as a Pydantic validator, lets the two drift. Invalid rows must be stored with their errors and row numbers, never dropped (`canonical-schema.md`), so validation has to report per row instead of failing the whole file.

Pandera's `PydanticModel` dtype was tried first. It runs the same Pydantic model row by row. When a row fails, the error says only "could not coerce", and a missing column is reported as a coercion error instead of a missing column.

## Decision

Every row rule lives only in the domain's Pydantic row model (strict mode, so `float` never becomes money). `SchemaSpec.frame_schema()` builds a Pandera schema for the file shape only: exactly the model's columns and no nulls. `SchemaSpec.validate_frame()` runs that schema lazily, so a malformed file raises one `SchemaErrors` that lists every failure. It then validates each row with Pydantic and returns the valid rows and a `RowError` (row number and messages) for each invalid row. Frames are Polars, as ADR 0001 and Iteration 2 assume.

## Alternatives considered

| Option | Why not |
|---|---|
| Rules in both Pandera checks and Pydantic | Two definitions of every money rule; they drift. |
| Pandera `PydanticModel` dtype | Unhelpful error messages, no per-row errors, and it iterates in Python anyway. |
| pandas backend | ADR 0001 and Iteration 2 assume Polars; pandas would be a second dataframe library. |

## Consequences

- **Positive:** each rule is defined once and tested once. Ingest gets per-row errors with row numbers.
- **Negative / cost:** row validation runs in Python, about one model call per row. This is fine for daily files of thousands of rows.
- **Follow-up:** if ingest profiling in Iteration 9 shows validation dominates, move hot, simple checks into vectorized Pandera checks and keep Pydantic as the reference.
