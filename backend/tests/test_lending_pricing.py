from datetime import date
from decimal import Decimal

import pytest

from kredpare.domains.lending.pricing import (
    DayCount,
    Rounding,
    accrual_days,
    accrued_interest,
    purchase_price,
)

UPB = Decimal("20300.00")
RATE = Decimal("0.099900")  # UPB x rate = 2027.97 per year


@pytest.mark.parametrize(
    ("start", "end", "convention", "inclusive", "days"),
    [
        (date(2026, 8, 20), date(2026, 9, 2), DayCount.ACTUAL_365, False, 13),
        (date(2026, 8, 20), date(2026, 9, 2), DayCount.ACTUAL_365, True, 14),
        (date(2026, 8, 20), date(2026, 9, 2), DayCount.THIRTY_360, False, 12),
        (date(2026, 8, 20), date(2026, 9, 2), DayCount.THIRTY_360, True, 13),
        # 30U/360: day 31 becomes 30 on both ends when the start is the 30th or 31st.
        (date(2026, 7, 31), date(2026, 8, 31), DayCount.THIRTY_360, False, 30),
        (date(2026, 7, 31), date(2026, 8, 31), DayCount.ACTUAL_365, False, 31),
        # ...but the end keeps 31 when the start is earlier in the month.
        (date(2026, 8, 15), date(2026, 8, 31), DayCount.THIRTY_360, False, 16),
        (date(2026, 9, 2), date(2026, 9, 2), DayCount.ACTUAL_365, False, 0),
    ],
)
def test_accrual_days(
    start: date, end: date, convention: DayCount, inclusive: bool, days: int
) -> None:
    assert accrual_days(start, end, convention, end_inclusive=inclusive) == days


def test_accrual_end_before_start_is_rejected() -> None:
    with pytest.raises(ValueError, match="before"):
        accrual_days(date(2026, 9, 2), date(2026, 9, 1), DayCount.ACTUAL_365)


@pytest.mark.parametrize(
    ("convention", "inclusive", "rounding", "expected"),
    [
        # 2027.97 x 13 / 365 = 72.2290...
        (DayCount.ACTUAL_365, False, Rounding.HALF_UP, "72.23"),
        (DayCount.ACTUAL_365, False, Rounding.TRUNCATE, "72.22"),
        # 2027.97 x 14 / 365 = 77.7851...
        (DayCount.ACTUAL_365, True, Rounding.HALF_UP, "77.79"),
        # 2027.97 x 12 / 360 = 67.599
        (DayCount.THIRTY_360, False, Rounding.HALF_UP, "67.60"),
        (DayCount.THIRTY_360, False, Rounding.TRUNCATE, "67.59"),
    ],
)
def test_accrued_interest(
    convention: DayCount, inclusive: bool, rounding: Rounding, expected: str
) -> None:
    result = accrued_interest(
        UPB,
        RATE,
        date(2026, 8, 20),
        date(2026, 9, 2),
        convention,
        end_inclusive=inclusive,
        rounding=rounding,
    )

    assert result == Decimal(expected)
    assert result.as_tuple().exponent == -2


def test_accrued_interest_exact_half_cent() -> None:
    # 182.50 x 0.01 x 1 / 365 = 0.005 exactly.
    args = (Decimal("182.50"), Decimal("0.010000"), date(2026, 9, 1), date(2026, 9, 2))

    assert accrued_interest(*args, DayCount.ACTUAL_365) == Decimal("0.01")
    assert accrued_interest(*args, DayCount.ACTUAL_365, rounding=Rounding.TRUNCATE) == Decimal(
        "0.00"
    )


def test_accrued_interest_defaults_to_half_up_and_exclusive_end() -> None:
    result = accrued_interest(UPB, RATE, date(2026, 8, 20), date(2026, 9, 2), DayCount.ACTUAL_365)

    assert result == Decimal("72.23")


def test_purchase_price_rounds_the_principal_part_half_up() -> None:
    assert purchase_price(UPB, Decimal("1.015000"), Decimal("72.23")) == Decimal("20676.73")
    # 100.50 x 1.010000 = 101.505 exactly.
    assert purchase_price(Decimal("100.50"), Decimal("1.010000"), Decimal("0.00")) == Decimal(
        "101.51"
    )
