"""Provider-neutral LLM client protocol and the per-model price table.

The workflow depends only on `LLMClient`. A provider is one adapter module plus one row in
`MODEL_PRICES`. Model ids come from settings or arguments, never from the flow.
"""

from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol

from pydantic import BaseModel

_MILLION = Decimal(1_000_000)


@dataclass(frozen=True)
class LLMResult[T: BaseModel]:
    parsed: T
    input_tokens: int
    output_tokens: int
    latency_seconds: float
    retries: int = 0
    """Requests repeated after a 429, 5xx, or connection error."""


class InvalidModelOutput(Exception):
    """The model replied, but not with JSON that validates against the schema. Never repaired."""

    def __init__(
        self,
        detail: str,
        *,
        input_tokens: int,
        output_tokens: int,
        latency_seconds: float,
        retries: int = 0,
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retries = retries
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_seconds = latency_seconds


class LLMUnavailable(Exception):
    """The provider could not be reached or kept failing after the retry cap.

    Not a verdict on the break: the caller leaves the break as it was and can rerun later.
    """

    def __init__(self, detail: str, *, retries: int) -> None:
        super().__init__(detail)
        self.retries = retries


class LLMClient(Protocol):
    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        """One call. InvalidModelOutput for a bad reply, LLMUnavailable when retries run out."""
        ...


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens, paid tier. Prompt-cache discounts are not applied."""

    input_per_million: Decimal
    output_per_million: Decimal
    source: str
    checked_on: str


_GEMINI_PRICING = "https://ai.google.dev/gemini-api/docs/pricing"

# Gemini API paid tier, Standard, text input; output includes thinking tokens. Both models have
# a free tier (rate-limited); the paid rate is recorded so the cost is what production would pay.
MODEL_PRICES: dict[str, ModelPrice] = {
    "gemini-3.5-flash-lite": ModelPrice(
        Decimal("0.30"), Decimal("2.50"), _GEMINI_PRICING, "2026-10-07"
    ),
    "gemini-3.5-flash": ModelPrice(Decimal("1.50"), Decimal("9.00"), _GEMINI_PRICING, "2026-10-07"),
}


class UnknownModelPrice(KeyError):
    pass


def cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    prices: dict[str, ModelPrice] | None = None,
) -> Decimal:
    """Exact cost, not rounded. An unpriced model raises: cost is never silently zero."""
    table = MODEL_PRICES if prices is None else prices
    try:
        price = table[model]
    except KeyError:
        raise UnknownModelPrice(f"no price for model {model!r}") from None
    return (
        Decimal(input_tokens) * price.input_per_million
        + Decimal(output_tokens) * price.output_per_million
    ) / _MILLION
