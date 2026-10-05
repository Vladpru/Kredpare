# 0011. Use DeepSeek for the workflow LLM behind a provider-neutral client

- **Status:** Accepted
- **Date:** 2026-10-05
- **Iteration:** M3

## Context

The workflow level (M3) makes one LLM call per break and must record accuracy and cost per model. The plan named Anthropic Haiku and Sonnet. The user only has DeepSeek API access, so `ANTHROPIC_API_KEY` will not exist. DeepSeek exposes an OpenAI-compatible chat completions API with a JSON output mode (`response_format: {"type": "json_object"}`). It has no schema-enforced structured output, so the reply must be validated by us. Per the DeepSeek docs on 2026-10-05 the current models are `deepseek-flash` and `deepseek-v4-pro`; thinking mode is on by default and can be switched with `thinking: {"type": "enabled" | "disabled"}`.

## Decision

- `core/cases/llm.py` defines a small `LLMClient` protocol: rendered prompt and output schema in, parsed `WorkflowExplanation` plus usage (tokens, latency) out. The flow, the tests, and the cache depend only on it.
- One adapter, `core/cases/deepseek.py`, talks to the OpenAI-compatible endpoint with the `openai` SDK. Base URL, API key, model id, and thinking mode come from settings; the flow never names a model.
- Output is requested in JSON mode, with the JSON schema in the system prompt, and validated with pydantic. Invalid JSON, a schema error, an empty reply, or a reply truncated at `max_tokens` becomes `needs_investigation` with the reason recorded. Values are never repaired.
- Prices live in one table keyed by model id, with the source URL and the date checked. DeepSeek publishes peak and half-price off-peak rates; the table uses the peak rate, so recorded cost is an upper bound. Cache-hit input is not discounted. A model without a row raises, so cost is never silently zero.
- Thinking mode is off by default (cheaper, and JSON mode is documented without it). It is a setting.
- The M3 model comparison becomes `deepseek-flash` against `deepseek-v4-pro`.

## Alternatives considered

| Option | Why not |
|---|---|
| Anthropic Haiku and Sonnet, as planned | No access. |
| Support both providers now | A second adapter with no way to test it against the real API. A row and a module can be added later. |
| LangChain or another abstraction layer | A plain protocol with one method is enough; the plan defers LangGraph/LangChain. |
| Raw HTTP instead of the `openai` SDK | `httpx` is not a runtime dependency; the SDK adds typed responses and retries for the one call we make. |

## Consequences

- **Positive:** the project can run real evals; switching or adding a provider touches one module and one price row.
- **Negative / cost:** no schema-constrained decoding, so invalid replies are possible and count against accuracy. Prices change; the table must be rechecked before each recorded eval. A new runtime dependency (`openai`).
- **Follow-up:** record the model comparison in `docs/evals.md`. Revisit if DeepSeek JSON mode proves unreliable (invalid-output rate in the eval) or if Anthropic access appears.
