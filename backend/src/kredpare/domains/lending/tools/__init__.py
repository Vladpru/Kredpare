"""Deterministic lending tools. Thin, typed wrappers over pricing.py; no math of their own."""

from datetime import date
from decimal import Decimal

from kredpare.domains.lending import pricing
from kredpare.domains.lending.pricing import DayCount, Rounding
from kredpare.domains.lending.tools.query_records import QueryRecords

__all__ = ["QueryRecords", "calc_accrued_interest", "recompute_purchase_price"]


def calc_accrued_interest(
    upb: Decimal,
    note_rate: Decimal,
    start: date,
    end: date,
    convention: DayCount,
    *,
    end_inclusive: bool = False,
    rounding: Rounding = Rounding.HALF_UP,
) -> Decimal:
    """Accrued interest in cents, rounded once with the given mode (default half-up)."""
    return pricing.accrued_interest(
        upb, note_rate, start, end, convention, end_inclusive=end_inclusive, rounding=rounding
    )


def recompute_purchase_price(upb: Decimal, price_pct: Decimal, accrued: Decimal) -> Decimal:
    """round_half_up(upb x price_pct, 2) + accrued."""
    return pricing.purchase_price(upb, price_pct, accrued)
