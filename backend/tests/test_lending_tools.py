from datetime import date
from decimal import Decimal

from kredpare.domains.lending.pricing import DayCount, Rounding, accrued_interest, purchase_price
from kredpare.domains.lending.tools import calc_accrued_interest, recompute_purchase_price

UPB = Decimal("20300.00")
RATE = Decimal("0.099900")
START, END = date(2026, 8, 20), date(2026, 9, 2)


def test_calc_accrued_interest_matches_pricing() -> None:
    for convention in DayCount:
        for rounding in Rounding:
            got = calc_accrued_interest(
                UPB, RATE, START, END, convention, end_inclusive=True, rounding=rounding
            )
            assert got == accrued_interest(
                UPB, RATE, START, END, convention, end_inclusive=True, rounding=rounding
            )
            assert isinstance(got, Decimal)


def test_calc_accrued_interest_known_value() -> None:
    # 20300 x 0.0999 x 13 / 365 = 72.2282... -> 72.23 half-up, 72.22 truncated
    args = (UPB, RATE, START, END, DayCount.ACTUAL_365)
    assert calc_accrued_interest(*args) == Decimal("72.23")
    assert calc_accrued_interest(*args, rounding=Rounding.TRUNCATE) == Decimal("72.22")


def test_recompute_purchase_price() -> None:
    accrued = Decimal("72.23")
    got = recompute_purchase_price(UPB, Decimal("1.015000"), accrued)
    assert got == purchase_price(UPB, Decimal("1.015000"), accrued)
    assert got == Decimal("20604.50") + accrued
