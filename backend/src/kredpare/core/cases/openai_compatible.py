"""Adapter for `LLMClient` over any OpenAI-compatible chat completions endpoint.

Used with Google's Gemini endpoint (docs/adr/0011-gemini-for-workflow-llm.md). Structured output
is requested as a strict `json_schema`; the reply is validated against the pydantic schema and
never repaired: invalid JSON, a schema error, an empty reply, or a reply cut off at `max_tokens`
raises `InvalidModelOutput`. 429, 5xx, and connection errors are retried with exponential
backoff up to a cap; running out of retries raises `LLMUnavailable`.
"""

import time
from collections.abc import Callable
from typing import Any

import openai
from pydantic import BaseModel, ValidationError

from kredpare.core.cases.llm import InvalidModelOutput, LLMResult, LLMUnavailable
from kredpare.core.settings import Settings

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT_SECONDS = 120.0


def _retryable(exc: Exception) -> bool:
    if isinstance(exc, openai.APIStatusError):
        return exc.status_code == 429 or exc.status_code >= 500
    return isinstance(exc, openai.APIConnectionError)


def _retry_after(exc: Exception) -> float | None:
    if not isinstance(exc, openai.APIStatusError):
        return None
    try:
        return float(exc.response.headers["retry-after"])
    except (KeyError, ValueError):
        return None


class OpenAICompatibleClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        json_schema: bool = True,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        max_retries: int = 5,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        client: Any = None,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        # The SDK's own retries are off: ours are counted and reported.
        self._client: Any = client or openai.OpenAI(
            api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS, max_retries=0
        )
        self._json_schema = json_schema
        self._max_tokens = max_tokens
        self._max_retries = max_retries
        self._base_delay = base_delay
        self._max_delay = max_delay
        self._sleep = sleep

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAICompatibleClient":
        if settings.llm_api_key is None:
            raise RuntimeError("GEMINI_API_KEY is not set")
        return cls(api_key=settings.llm_api_key.get_secret_value(), base_url=settings.llm_base_url)

    def _response_format(self, schema: type[BaseModel]) -> dict[str, Any]:
        if not self._json_schema:
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {
                "name": schema.__name__,
                "schema": schema.model_json_schema(),
                "strict": True,
            },
        }

    def _create(self, **request: Any) -> tuple[Any, int]:
        """The response and how many requests were repeated to get it."""
        retries = 0
        while True:
            try:
                response = self._client.chat.completions.create(**request)
                return response, retries
            except Exception as exc:
                if not _retryable(exc):
                    raise LLMUnavailable(f"{type(exc).__name__}: {exc}", retries=retries) from None
                if retries >= self._max_retries:
                    raise LLMUnavailable(
                        f"gave up after {retries} retries: {type(exc).__name__}", retries=retries
                    ) from None
                delay = _retry_after(exc) or self._base_delay * 2**retries
                self._sleep(min(delay, self._max_delay))
                retries += 1

    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        started = time.perf_counter()
        response, retries = self._create(
            model=model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format=self._response_format(schema),
            max_tokens=self._max_tokens,
        )
        latency = time.perf_counter() - started
        usage = response.usage
        if usage is None:
            raise RuntimeError("response carried no usage; cost cannot be computed")
        input_tokens, output_tokens = usage.prompt_tokens, usage.completion_tokens

        def invalid(detail: str) -> InvalidModelOutput:
            return InvalidModelOutput(
                detail,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
                retries=retries,
            )

        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise invalid("reply truncated at max_tokens")
        content = choice.message.content
        if not content or not content.strip():
            raise invalid("empty reply")
        try:
            parsed = schema.model_validate_json(content)
        except ValidationError as exc:
            raise invalid(f"reply does not match the schema: {_summary(exc)}") from None
        return LLMResult(parsed, input_tokens, output_tokens, latency, retries)


def _summary(exc: ValidationError) -> str:
    """Field paths and error kinds only: the reply text itself is not echoed into reasons."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['type']}" for e in exc.errors()
    )
