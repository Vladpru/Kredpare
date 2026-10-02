# Glossary

Terms used in Kredpare code, docs, and prompts. All names, numbers, and examples are synthetic.

Each lending term notes its **core name** when `core/` uses a generic word for it. `core/` must use only the generic name.

## Lending domain (`domains/lending/`)

**Forward flow.** An ongoing arrangement where the seller sells newly originated loans to a counterparty on a regular schedule (for example, weekly) under one agreement, instead of one large one-time portfolio sale. Every sale batch must be reconciled.

**Seller.** The company running Kredpare. It originates (funds) loans and sells them. Also called the originator.

**Counterparty.** The buyer of the loans (investor, bank, credit fund), or another party that exchanges files with the seller, such as a servicer. *Core name: `counterparty`.* Never "lender" or "partner" in code.

**Dealer.** The auto dealership where the borrower signed the retail installment contract. One dealer produces many loans. Relevant because some breaks affect every loan from one dealer.

**Loan.** A single consumer auto installment loan. *Core name: `record`.*

**Agreement.** The legal document that governs the sale: eligibility criteria, purchase price formula, accrued interest rules, settlement timing, repurchase obligations. In forward flow it is often called a Loan Sale Agreement or Forward Flow Agreement. *Core name: `agreement`.*

**Amendment.** A later document that changes specific sections of the agreement from its **effective date** onward. The older text still applies to sales before that date. Finding the clause in force on a given date is a core RAG task.

**Effective date.** The date from which an agreement or amendment section applies.

**Supersedes.** Relationship between an amendment section and the earlier section it replaces.

**Funding date.** The date the seller disbursed loan proceeds (paid the dealer). Interest starts accruing from this date.

**Funded amount.** The principal disbursed on the funding date. In Kredpare this is the original principal balance.

**Unpaid principal balance (UPB).** Principal still owed on a loan on a given date. At sale time it equals the funded amount minus any principal the borrower has already paid.

**Note rate.** The annual interest rate on the loan contract, used to calculate accrued interest. (APR includes fees and is not used for these calculations.)

**Cut-off date.** The date on which loan balances are frozen for a sale batch. Balances in the sale files are "as of" the cut-off date.

**Purchase date / settlement date.** The date the counterparty pays the seller for a batch. Accrued interest is calculated up to this date (the exact end date is defined per agreement).

**Accrued interest.** Interest earned on a loan but not yet paid by the borrower, from the accrual start date (funding date, or the last paid-to date) to the settlement date. The buyer pays it to the seller as part of the purchase price.

```
accrued_interest = UPB × note_rate × days / day_count_basis
```

**Day-count convention.** How `days` and `day_count_basis` are counted. Common options: **Actual/365** (actual calendar days, basis 365) and **30/360** (every month counts as 30 days, basis 360). Each agreement fixes one convention; an amendment can change it.

**Par.** A price of 100% of UPB.

**Premium / discount.** A purchase price above par (premium, for example 101.50%) or below par (discount, for example 98.75%). The percentage can depend on loan attributes such as credit tier or term, as defined in the agreement's pricing grid.

**Purchase price.** What the counterparty pays the seller for one loan:

```
purchase_price = UPB × price_pct + accrued_interest
```

Example: UPB $20,000.00 at 101.50% = $20,300.00. Note rate 9.99%, 12 days, Actual/365: accrued interest = $65.69. Purchase price = $20,365.69. Rounding rule (per loan, half-up to cents) is defined in the agreement.

**Funded loan file.** The seller's file listing loans offered in a sale batch: loan id, dealer, funding date, funded amount, UPB, note rate, term. *Lending schema: `FundedLoan`.*

**Purchase confirmation.** The counterparty's file confirming which loans it bought and what it paid: loan id, UPB, price %, accrued interest, purchase price, settlement date. *Lending schema: `PurchaseConfirmation`.*

**Servicer.** The party that collects borrower payments after the sale. It may be the seller or a third party.

**Servicer onboarding file.** The servicer's file confirming the loans it has boarded (set up for servicing) with their balances and next payment dates. *Lending schema: `ServicerOnboarding`.*

**Eligibility criteria.** Loan attributes the agreement requires for a loan to be sold (for example, maximum term, minimum credit score). A loan that fails them may be rejected or must be repurchased.

**Repurchase.** The seller buys a loan back from the counterparty, for example because it breached eligibility criteria.

**True-up.** A later payment that corrects a settlement difference between seller and counterparty.

## Reconciliation and Kredpare (`core/`)

**Reconciliation.** Comparing files from two or more parties to confirm they agree on the same records and amounts.

**Record.** One row in a canonical file, for example one loan in one file. Identified by a match key.

**Canonical record.** A record after mapping, normalization, and validation into the canonical schema. See `docs/domain/canonical-schema.md`.

**Match key.** The fields used to pair records across files (for example, `record_id`, with `counterparty_id`).

**Break.** A discrepancy found by matching: a missing record, a different amount, a different date, and so on. Each break has a type. See `docs/domain/break-taxonomy.md`.

**Tolerance.** The maximum difference treated as a match (for example, $0.01 for rounding). Defined per comparison rule.

**Mapping config.** A versioned configuration that maps a counterparty's source columns to canonical fields, with a transform for each column. States: `proposed → approved → superseded`.

**Header hash.** sha256 of a file's normalized column headers. A known hash selects an approved mapping config; an unknown hash triggers an LLM mapping proposal.

**Transform.** A function from a fixed enum that converts a source value to a canonical value (for example, `parse_usd`, `cents_to_decimal`, `parse_date_mdy`).

**Cascade.** The order in which Kredpare tries to explain a break: **rules (code) → workflow (RAG + 1 LLM call) → agent → escalate**. Each level only receives breaks the previous level could not close.

**Cascade level.** The level that closed a break: `rule`, `workflow`, `agent`, or `escalated`.

**Rule.** Deterministic code that explains a known break pattern. Result: `explained` or `not_explained`.

**Workflow.** A fixed sequence: break → search the agreement → one LLM call → explanation.

**Agent.** An LLM investigator that chooses its own tool calls, limited by an attempt counter and a budget. Used only for breaks in `needs_investigation`.

**Escalation.** Handing a break to a human because no level could explain it with enough confidence.

**Explanation.** The output of a cascade level: root cause, citation, and confidence.

**Citation.** A reference to the agreement section (and version) that supports an explanation.

**Confidence.** A score from 0 to 1 attached to an explanation. Below the threshold, the break moves to the next cascade level.

**Case.** The lifecycle of one break after detection: explanation, proposal, human decision, apply or email, counterparty reply, resolution. One case is one LangGraph thread.

**Proposal.** What Kredpare suggests doing about an explained break: a correction or an email to the counterparty.

**Correction.** A deterministic data fix applied after approval, with an idempotency key.

**HITL (human in the loop).** A step where a human must approve. HITL #1: approve a mapping config. HITL #2: approve, reject, or comment on a proposal.

**Rule candidate.** A new root cause the agent found several times and a human confirmed. A developer moves it into code as a new rule.

**Difficulty level.** Label on an injected break: `simple` (closed by a rule), `medium` (needs the agreement), `hard` (needs the agent).

**Ground truth.** The datagen output (`ground_truth.jsonl`) listing every injected break with its type, cause, and difficulty level. Evals compare against it.

**Audit event.** An append-only row in `audit_events` recording a state change: actor, before and after, `model`, `prompt_version`, `trace_id`, and a hash chain (`prev_hash → hash`).

**Domain spec (`DomainSpec`).** The interface a domain uses to register its schemas, break types, rules, tools, and prompts with `core/`.
