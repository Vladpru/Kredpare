"""DeepSeek adapter for `LLMClient`: OpenAI-compatible chat completions in JSON output mode.

The reply is validated against the pydantic schema and never repaired: invalid JSON, a schema
error, an empty reply, or a truncated reply raises `InvalidModelOutput`.
"""

import json
import time
from typing import Any

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from kredpare.core.cases.llm import InvalidModelOutput, LLMResult
from kredpare.core.settings import Settings

DEFAULT_MAX_TOKENS = 4096
DEFAULT_TIMEOUT_SECONDS = 120.0


class DeepSeekClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        thinking: bool = False,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        client: Any = None,
    ) -> None:
        self._client = client or OpenAI(
            api_key=api_key, base_url=base_url, timeout=DEFAULT_TIMEOUT_SECONDS
        )
        self._thinking = thinking
        self._max_tokens = max_tokens

    @classmethod
    def from_settings(cls, settings: Settings) -> "DeepSeekClient":
        if settings.deepseek_api_key is None:
            raise RuntimeError("DEEPSEEK_API_KEY is not set")
        return cls(
            api_key=settings.deepseek_api_key.get_secret_value(),
            base_url=settings.deepseek_base_url,
            thinking=settings.workflow_thinking,
        )

    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        schema_text = json.dumps(schema.model_json_schema())
        started = time.perf_counter()
        response = self._client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": f"{system}\n\njson schema of the reply:\n{schema_text}",
                },
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            max_tokens=self._max_tokens,
            extra_body={"thinking": {"type": "enabled" if self._thinking else "disabled"}},
        )
        latency = time.perf_counter() - started
        usage = response.usage
        if usage is None:
            raise RuntimeError("DeepSeek response carried no usage; cost cannot be computed")
        input_tokens, output_tokens = usage.prompt_tokens, usage.completion_tokens

        def invalid(detail: str) -> InvalidModelOutput:
            return InvalidModelOutput(
                detail,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                latency_seconds=latency,
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
        return LLMResult(parsed, input_tokens, output_tokens, latency)


def _summary(exc: ValidationError) -> str:
    """Field paths and error kinds only: the reply text itself is not echoed into reasons."""
    return "; ".join(
        f"{'.'.join(str(p) for p in e['loc']) or '<root>'}: {e['type']}" for e in exc.errors()
    )
