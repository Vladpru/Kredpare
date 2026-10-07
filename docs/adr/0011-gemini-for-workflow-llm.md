# 0011. Use Gemini for the workflow LLM behind a provider-neutral client

- **Status:** Accepted
- **Date:** 2026-10-07
- **Iteration:** M3

## Context

The workflow level (M3) makes one LLM call per break that rules could not close, and must record accuracy and cost per model. The plan named Anthropic Haiku and Sonnet. The user has no Anthropic access, and the DeepSeek and Agent Router keys they tried returned 401. They do have a Google AI Studio (Gemini API) key. Google exposes an OpenAI-compatible chat completions endpoint (`https://generativelanguage.googleapis.com/v1beta/openai/`) that accepts `response_format: {"type": "json_schema", ...}`; this was confirmed with a real call to `gemini-3.5-flash-lite`. The free tier is rate-limited (HTTP 429).

## Decision

- `core/cases/llm.py` defines a small `LLMClient` protocol: rendered prompt and output schema in, parsed `WorkflowExplanation` plus usage (tokens, latency, retries) out. The flow, the tests, and the cache depend only on it.
- One adapter, `core/cases/openai_compatible.py`, talks to any OpenAI-compatible endpoint with the `openai` SDK. Base URL, API key (`GEMINI_API_KEY`), and model id come from settings or arguments; the flow never names a model.
- Output is requested as a strict `json_schema` (JSON object mode is a constructor option for providers without it) and validated with pydantic. Invalid JSON, a schema error, an empty reply, or a reply cut off at `max_tokens` becomes `needs_investigation` with the reason recorded. Values are never repaired.
- 429, 5xx, and connection errors are retried with exponential backoff, honouring `Retry-After`, capped in delay and in count. The retry count is recorded in usage and in the audit event. When retries run out the break is left in `pending_workflow` and the run reports it, so a rerun picks it up; it is not marked `needs_investigation`.
- Prices live in one table keyed by model id, with the source URL and the date checked (2026-10-07, <https://ai.google.dev/gemini-api/docs/pricing>): `gemini-3.5-flash-lite` $0.30 in / $2.50 out per 1M tokens, `gemini-3.5-flash` $1.50 in / $9.00 out (paid tier, Standard, output includes thinking tokens). Both models also have a free tier; recorded cost is what the paid tier would charge. A model without a row raises, so cost is never silently zero.
- The primary model is `gemini-3.5-flash-lite`. The M3 comparison is `gemini-3.5-flash-lite` against `gemini-3.5-flash`.
- The workflow does not call the model when no clause-supported candidate reproduces the counterparty value: the result is `needs_investigation` (`no_supported_candidate`) at zero cost, with `llm_called=False` in usage and in the audit payload. The eval reports how many breaks reached the LLM; cost per break (S7) is computed over breaks that reached the workflow, and records how many of those were short-circuited.

## Alternatives considered

| Option | Why not |
|---|---|
| Anthropic Haiku and Sonnet, as planned | No access. |
| DeepSeek, then Agent Router | Keys returned 401. |
| A Gemini-native SDK | Locks the adapter to one vendor; the OpenAI-compatible endpoint keeps the adapter generic. |
| LangChain or another abstraction layer | A plain protocol with one method is enough; the plan defers LangGraph/LangChain. |

## Consequences

- **Positive:** the project can run real evals on a free-tier key; adding a provider is one price row, plus an adapter only if it is not OpenAI-compatible.
- **Negative / cost:** the OpenAI-compatibility layer is a beta surface of Google's API; free-tier rate limits slow eval runs; a new runtime dependency (`openai`). Prices change, so the table must be rechecked before each recorded eval.
- **Follow-up:** record the model comparison in `docs/evals.md`. Revisit if invalid-output rate is high for either model.
