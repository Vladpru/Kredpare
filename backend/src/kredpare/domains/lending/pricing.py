"""Deterministic loan pricing math. The only place lending amounts are computed."""

from datetime import date
from decimal import ROUND_DOWN, ROUND_HALF_UP, Decimal
from enum import StrEnum

from kredpare.core.canonical import round_half_up_cents

_CENT = Decimal("0.01")


class DayCount(StrEnum):
    ACTUAL_365 = "actual/365"
    THIRTY_360 = "30/360"
    """30U/360 bond basis: a 31st becomes the 30th; an end 31st only when the start is 30th+."""


class Rounding(StrEnum):
    HALF_UP = "half_up"
    TRUNCATE = "truncate"


_ROUNDING_MODES = {Rounding.HALF_UP: ROUND_HALF_UP, Rounding.TRUNCATE: ROUND_DOWN}
_YEAR_DAYS = {DayCount.ACTUAL_365: 365, DayCount.THIRTY_360: 360}


def accrual_days(
    start: date, end: date, convention: DayCount, *, end_inclusive: bool = False
) -> int:
    """Days from start (inclusive) to end (exclusive unless end_inclusive)."""
    if end < start:
        raise ValueError(f"accrual end {end} is before start {start}")
    if convention is DayCount.ACTUAL_365:
        days = (end - start).days
    else:
        d1 = min(start.day, 30)
        d2 = min(end.day, 30) if d1 == 30 else end.day
        days = 360 * (end.year - start.year) + 30 * (end.month - start.month) + (d2 - d1)
    return days + 1 if end_inclusive else days


def accrued_interest(
    upb: Decimal,
    note_rate: Decimal,
    start: date,
    end: date,
    convention: DayCount,
    *,
    end_inclusive: bool = False,
    rounding: Rounding = Rounding.HALF_UP,
) -> Decimal:
    """upb x rate x days / year days, rounded once, per loan, to cents."""
    days = accrual_days(start, end, convention, end_inclusive=end_inclusive)
    exact = upb * note_rate * days / _YEAR_DAYS[convention]
    return exact.quantize(_CENT, rounding=_ROUNDING_MODES[rounding])


def purchase_price(upb: Decimal, price_pct: Decimal, accrued: Decimal) -> Decimal:
    """round_half_up(upb x price_pct, 2) + accrued interest."""
    return round_half_up_cents(upb * price_pct) + accrued
