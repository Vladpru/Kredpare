# Counterparties

Status: **approved** 2026-10-05. Every name, id, number, and agreement term below is invented. Any resemblance to a real company is accidental.

## Parties

| Id | Name | Role | Files it sends |
|---|---|---|---|
| — | Larkspan Auto Finance | **Seller** (runs Kredpare) | `FundedLoan`, one file per batch per buyer |
| `cp-quillmont` | Quillmont Credit Fund | Buyer | `PurchaseConfirmation` |
| `cp-brackwater` | Brackwater Bank | Buyer | `PurchaseConfirmation` |
| `cp-tessaline` | Tessaline Capital | Buyer | `PurchaseConfirmation` |
| `cp-orlo` | Orlo Servicing | Servicer for all three buyers | `ServicerOnboarding` |

The plan asks for 3 counterparties. They are the three buyers. Orlo is a fourth, simple party with one stable format, because `ServicerOnboarding` needs a sender. It has no agreement in the RAG corpus.

## File formats

All files are CSV, UTF-8, one header row. The seller file uses the canonical names and ISO formats.

| | Quillmont | Brackwater | Tessaline | Orlo |
|---|---|---|---|---|
| Delimiter | `,` | `;` | `,` | `,` |
| Date format | `MM/DD/YYYY` (`09/02/2026`) | `YYYYMMDD` (`20260902`) | `DD-Mon-YYYY` (`02-Sep-2026`) | ISO (`2026-09-02`) |
| Money format | `"$1,234.50"` | cents as int (`123450`) | plain decimal (`1234.50`) | plain decimal |
| Price format | percent (`101.500`) | fraction (`1.015000`) | percent (`101.50`) | — |
| Batch column | none (from upload metadata) | none | `Batch Ref` | — |

Column names, in file order:

| Canonical field | Quillmont | Brackwater | Tessaline | Orlo |
|---|---|---|---|---|
| `loan_id` | `Loan Number` | `ACCT_ID` | `Loan ID` (3rd) | `loan_id` |
| `settlement_date` | `Settle Date` | `PURCH_DT` | `Settlement` (1st) | — |
| `upb` | `Principal Balance` | `UPB_CENTS` | `Current Balance` | `boarded_upb` |
| `price_pct` | `Purchase Price %` | `PX` | `Price` | — |
| `accrued_interest` | `Accrued Int` | `ACCR_INT_CENTS` | `Interest Accrued` | — |
| `purchase_price` | `Total Price` | `PROCEEDS_CENTS` | `Wire Amount` | — |
| `batch_id` | — | — | `Batch Ref` (2nd) | — |
| `boarded_date` | — | — | — | `board_dt` |
| `next_payment_due_date` | — | — | — | `first_due` |

Iteration 3 adds 20–30 mutated variants of these formats (renamed columns, reordered columns, new date formats).

## Agreement structure (all three buyers)

Same section numbering, so citations are comparable:

- §3 Eligibility
- §4 Purchase price: §4.1 pricing grid, §4.2 accrued interest, §4.3 rounding
- §5 Settlement: §5.1 schedule, §5.2 business day convention
- §6 Confirmation: §6.1 confirmation deadline

Each buyer has a base agreement and 2 amendments. An amendment replaces specific sections from its effective date.

## Agreement terms

### Quillmont Credit Fund

| Term | Base agreement | Amendment 1 (effective 2026-06-01) | Amendment 2 (effective 2026-09-01) |
|---|---|---|---|
| §4.1 pricing grid | A 102.00%, B 101.50%, C 100.75%, D 99.50% | — | **Tier B → 101.00%** |
| §4.2 accrued interest | Actual/365, from `funding_date` (inclusive) to `settlement_date` (exclusive) | — | — |
| §4.3 rounding | Per loan, half-up to cents | — | — |
| §5.1 schedule | Weekly, Wednesday | — | — |
| §5.2 business day | Not specified | **Following business day** | — |
| §6.1 confirmation | 5 business days after cut-off | — | — |

### Brackwater Bank

| Term | Base agreement | Amendment 1 (effective 2026-08-24) | Amendment 2 (effective 2026-10-01) |
|---|---|---|---|
| §3 eligibility | Tiers A–D | — | **Tier D not eligible** (not yet in force in the data window) |
| §4.1 pricing grid | A 101.75%, B 101.25%, C 100.50%, D 99.00% | — | — |
| §4.2 accrued interest | **30/360**, from `funding_date` to `settlement_date` | **Actual/365** | — |
| §4.3 rounding | Per loan, half-up to cents | — | — |
| §5.1 schedule | 15th and last business day of the month | — | — |
| §5.2 business day | Following business day | — | — |
| §6.1 confirmation | 5 business days after cut-off | — | — |

### Tessaline Capital

| Term | Base agreement | Amendment 1 (effective 2026-08-24) | Amendment 2 (effective 2026-07-01) |
|---|---|---|---|
| §4.1 pricing grid | A 102.25%, B 101.50%, C 101.00%, D 99.75% | **Tier C → 100.50%** | — |
| §4.2 accrued interest | Actual/365, from `funding_date` to `settlement_date` (exclusive) | — | — |
| §4.3 rounding | Per loan, half-up to cents | — | — |
| §5.1 schedule | Weekly, Friday | — | — |
| §6.1 confirmation | 5 business days after cut-off | — | — |
| Structure | — | — | **Renumbers §4.2 as §4.4 and adds a definitions section**; Amendment 1 then refers to the new numbers |

Amendment 2 of Tessaline is numbered after Amendment 1 but is effective earlier. Both are deliberate RAG traps (see below).

Cut-off date for every buyer: 2 business days before the settlement date.

## Data window and batches

Default datagen window: **2026-08-10 to 2026-09-08** (30 days, `--days 30`). US federal holidays apply (Labor Day, 2026-09-07).

| Buyer | Settlement dates in the window |
|---|---|
| Quillmont | Wed 08-12, 08-19, 08-26, 09-02 |
| Brackwater | Mon 08-17 (the 15th is a Saturday, rolled), Mon 08-31 |
| Tessaline | Fri 08-14, 08-21, 08-28, 09-04 |

## Where each break cause lives

| Cause | Difficulty | Counterparty | Why there |
|---|---|---|---|
| `loan_not_confirmed`, `loan_not_offered`, `duplicate_row`, `confirmation_overdue` | simple | all | Generic. |
| `settlement_date_roll` | simple | Brackwater | 08-15 is a Saturday; one side keeps the unrolled date. |
| `rounding_difference` | simple | Brackwater | Its cents-as-int system truncates. |
| `accrual_start_alternative` | simple | Tessaline | Accrues from the cut-off date. |
| `accrued_interest_error` | medium | Brackwater | Amendment 1 switches 30/360 → Actual/365 between the 08-17 and 08-31 batches. |
| `price_grid_amendment` | medium | Quillmont, Tessaline | Quillmont Tier B from 09-02; Tessaline Tier C from 08-28. |
| `dealer_wide_adjustment` | hard | Tessaline | One dealer's loans priced one tier lower in one batch. |
| `combined_causes` | hard | Brackwater | Amendment 1 day-count **and** truncation on the same loan. |
| `unannounced_rule_change` | hard | Quillmont | From the 08-26 batch, Quillmont counts the settlement day (inclusive end) with no amendment. §4.2 still says exclusive. |

## RAG traps (for the Iteration 4 golden set)

- **Effective date vs batch date:** Brackwater Amendment 1 applies to the 08-31 batch, not to 08-17.
- **Not yet in force:** Brackwater Amendment 2 exists in the corpus but must not be cited for any batch in the window.
- **Numbering vs effective order:** Tessaline Amendment 2 is effective before Amendment 1.
- **Renumbered sections:** after Tessaline Amendment 2, accrued interest is §4.4, not §4.2.
- **No clause at all:** Quillmont's unannounced change has no supporting clause. The correct answer cites the clause being violated.

## Decisions

- Orlo Servicing is a separate, fourth party with one stable format. Approved 2026-10-02.
- Default datagen window: 2026-08-10 to 2026-09-08. Approved 2026-10-02.
- Quillmont's 09-02 batch: Tier B loans carry only `price_grid_amendment`; `unannounced_rule_change` covers every other Quillmont loan from the 08-26 batch on. Keeps one cause per loan. Approved 2026-10-05.
- `combined_causes` and `accrued_interest_error` share the Brackwater 08-31 batch on different loans. Combined loans are picked so that neither cause alone reproduces the counterparty value.
