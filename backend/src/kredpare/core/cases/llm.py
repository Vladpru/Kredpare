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


class InvalidModelOutput(Exception):
    """The model replied, but not with JSON that validates against the schema. Never repaired."""

    def __init__(
        self, detail: str, *, input_tokens: int, output_tokens: int, latency_seconds: float
    ) -> None:
        super().__init__(detail)
        self.detail = detail
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.latency_seconds = latency_seconds


class LLMClient(Protocol):
    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        """One call. Raises InvalidModelOutput when the reply does not validate."""
        ...


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens. Input is the cache-miss price; cache hits are not discounted."""

    input_per_million: Decimal
    output_per_million: Decimal
    source: str
    checked_on: str


_DEEPSEEK_PRICING = "https://api-docs.deepseek.com/quick_start/pricing"

# DeepSeek publishes a peak and an off-peak (half) rate. The peak rate is used, so recorded
# cost is an upper bound.
MODEL_PRICES: dict[str, ModelPrice] = {
    "deepseek-flash": ModelPrice(Decimal("0.30"), Decimal("1.20"), _DEEPSEEK_PRICING, "2026-10-05"),
    "deepseek-v4-pro": ModelPrice(
        Decimal("1.32"), Decimal("3.96"), _DEEPSEEK_PRICING, "2026-10-05"
    ),
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
