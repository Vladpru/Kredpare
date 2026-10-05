from datetime import date

import pytest

from kredpare.domains.lending.calendar import (
    add_business_days,
    following_business_day,
    is_business_day,
    last_business_day_of_month,
)


@pytest.mark.parametrize(
    ("day", "expected"),
    [
        (date(2026, 9, 4), True),  # Friday
        (date(2026, 9, 5), False),  # Saturday
        (date(2026, 9, 6), False),  # Sunday
        (date(2026, 9, 7), False),  # Labor Day
        (date(2026, 7, 3), False),  # Independence Day observed
        (date(2026, 9, 8), True),
    ],
)
def test_is_business_day(day: date, expected: bool) -> None:
    assert is_business_day(day) is expected


def test_following_business_day_rolls_weekends_and_holidays() -> None:
    assert following_business_day(date(2026, 8, 15)) == date(2026, 8, 17)
    assert following_business_day(date(2026, 9, 5)) == date(2026, 9, 8)
    assert following_business_day(date(2026, 9, 2)) == date(2026, 9, 2)


def test_add_business_days_skips_weekends_and_holidays() -> None:
    assert add_business_days(date(2026, 9, 2), -2) == date(2026, 8, 31)
    assert add_business_days(date(2026, 9, 8), -2) == date(2026, 9, 3)  # skips Labor Day
    assert add_business_days(date(2026, 9, 4), 1) == date(2026, 9, 8)
    assert add_business_days(date(2026, 9, 4), 0) == date(2026, 9, 4)


def test_last_business_day_of_month() -> None:
    assert last_business_day_of_month(2026, 8) == date(2026, 8, 31)
    assert last_business_day_of_month(2026, 10) == date(2026, 10, 30)  # 31st is a Saturday
