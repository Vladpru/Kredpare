"""Canonical value types and the base record every domain schema maps into.

See docs/domain/canonical-schema.md. Values arrive already converted by transforms;
nothing here rounds. A value that needs rounding to fit its scale is rejected.
"""

from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, StringConstraints

_CENT = Decimal("0.01")
_MICRO = Decimal("0.000001")


def _fixed_scale(quantum: Decimal, places: int) -> AfterValidator:
    def check(value: Decimal) -> Decimal:
        if not value.is_finite():
            raise ValueError("must be a finite number")
        scaled = value.quantize(quantum)
        if scaled != value:
            raise ValueError(f"must have at most {places} decimal places, got {value}")
        return scaled

    return AfterValidator(check)


Money = Annotated[Decimal, Field(strict=True), _fixed_scale(_CENT, 2)]
"""USD amount with exactly 2 decimal places."""

Ratio = Annotated[Decimal, Field(strict=True), _fixed_scale(_MICRO, 6)]
"""A fraction (rate, price as a fraction of balance) with exactly 6 decimal places."""

Id = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
"""Trimmed, case preserved, never blank."""


def round_half_up_cents(value: Decimal) -> Decimal:
    """Round to cents, half away from zero (ROUND_HALF_UP)."""
    return value.quantize(_CENT, rounding=ROUND_HALF_UP)


class MatchStatus(StrEnum):
    UNMATCHED = "unmatched"
    MATCHED = "matched"
    IN_BREAK = "in_break"


class CanonicalRecord(BaseModel):
    """Generic envelope of one valid source row. Holds no domain fields."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_id: Id
    counterparty_id: Id
    batch_id: Id
    file_id: UUID
    row_number: Annotated[int, Field(ge=1)]
    schema_name: Id
    match_status: MatchStatus = MatchStatus.UNMATCHED
