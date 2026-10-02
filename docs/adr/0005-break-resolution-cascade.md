# 0005. Resolve breaks through a cascade: rules, workflow, agent, escalation

- **Status:** Accepted
- **Date:** 2026-10-02
- **Iteration:** −1

## Context

Most reconciliation breaks have known, mechanical causes (missing record, rounding, duplicate). Some need the agreement text. A few need investigation across many records. Sending every break to an LLM agent is slow, expensive, harder to audit, and can produce confident invented explanations. Money must only be computed by code.

## Decision

Every break goes through levels in order, and a level only receives what the previous one could not close:

1. **Rules** — deterministic code, no LLM. Result `explained` or `not_explained`.
2. **Workflow** — fixed steps: search the agreement, one LLM call, an explanation with a citation and a confidence.
3. **Agent** — only for breaks in `needs_investigation`, with an attempt limit and a budget per case.
4. **Escalate** — a human queue.

LLMs never compute amounts; they call deterministic tools. The share of breaks closed at each level, with accuracy and cost per level, is the project's primary metric. The agent must justify itself with eval numbers against the workflow on the hard set (Iteration 7).

## Alternatives considered

| Option | Why not |
|---|---|
| Agent for every break | Cost and latency on easy breaks; weaker auditability; no evidence the agent is needed. |
| Rules only | Cannot read agreements or amendments; medium and hard breaks stay manual. |
| Workflow only | Hard breaks need cross-record queries; the workflow would invent explanations or escalate everything hard. |

## Consequences

- **Positive:** cheap, auditable handling of the majority; LLM cost concentrated where it adds value; a clear README table.
- **Negative / cost:** confidence thresholds must be calibrated; three code paths to test.
- **Follow-up:** confirmed agent findings become rule candidates, moving the long tail down the cascade over time.
