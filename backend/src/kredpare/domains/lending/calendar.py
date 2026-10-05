"""US bank business days: weekdays that are not US federal holidays (observed dates included)."""

import calendar
from datetime import date, timedelta
from functools import cache

import holidays


@cache
def _federal_holidays(year: int) -> frozenset[date]:
    return frozenset(holidays.country_holidays("US", years=year))


def is_business_day(day: date) -> bool:
    return day.weekday() < 5 and day not in _federal_holidays(day.year)


def following_business_day(day: date) -> date:
    while not is_business_day(day):
        day += timedelta(days=1)
    return day


def add_business_days(day: date, count: int) -> date:
    """Move count business days forward (count > 0) or backward (count < 0)."""
    step = timedelta(days=1 if count > 0 else -1)
    remaining = abs(count)
    while remaining:
        day += step
        if is_business_day(day):
            remaining -= 1
    return day


def last_business_day_of_month(year: int, month: int) -> date:
    day = date(year, month, calendar.monthrange(year, month)[1])
    while not is_business_day(day):
        day -= timedelta(days=1)
    return day


class UsBankCalendar:
    """The calendar the lending domain gives core matching for ageing pending records."""

    def add_business_days(self, day: date, count: int) -> date:
        return add_business_days(day, count)


US_BANK_CALENDAR = UsBankCalendar()
