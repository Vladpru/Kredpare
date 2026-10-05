"""Agreement terms and settlement schedules from docs/domain/counterparties.md.

This is the generator's ground truth for what each agreement says on a given date.
Amendments apply in effective-date order, not in numbering order.
"""

from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from kredpare.domains.lending.calendar import (
    add_business_days,
    following_business_day,
    last_business_day_of_month,
)
from kredpare.domains.lending.pricing import DayCount

Tier = Literal["A", "B", "C", "D"]
TIERS: tuple[Tier, ...] = ("A", "B", "C", "D")

QUILLMONT = "cp-quillmont"
BRACKWATER = "cp-brackwater"
TESSALINE = "cp-tessaline"
ORLO = "cp-orlo"
BUYERS = (QUILLMONT, BRACKWATER, TESSALINE)

ROUNDING_CITATION = "base §4.3"
"""Every buyer: per loan, half-up to cents."""


@dataclass(frozen=True)
class Terms:
    pricing_grid: Mapping[Tier, Decimal]
    pricing_citation: str
    day_count: DayCount
    accrual_citation: str
    eligible_tiers: frozenset[Tier] = field(default=frozenset(TIERS))


@dataclass(frozen=True)
class _Version:
    effective: date
    label: str
    pricing: Mapping[Tier, Decimal] | None = None
    day_count: DayCount | None = None
    accrual_section: str | None = None
    """A renumbering moves the accrued interest clause without changing its rule."""
    eligible_tiers: frozenset[Tier] | None = None


def _grid(a: str, b: str, c: str, d: str) -> dict[Tier, Decimal]:
    return {"A": Decimal(a), "B": Decimal(b), "C": Decimal(c), "D": Decimal(d)}


_BASE_EFFECTIVE = date(2026, 1, 1)

_AGREEMENTS: dict[str, tuple[Terms, tuple[_Version, ...]]] = {
    QUILLMONT: (
        Terms(
            _grid("1.020000", "1.015000", "1.007500", "0.995000"),
            "base §4.1",
            DayCount.ACTUAL_365,
            "base §4.2",
        ),
        (
            # Amendment 1 only sets the business day convention (following).
            _Version(
                date(2026, 9, 1),
                "amendment-2",
                pricing=_grid("1.020000", "1.010000", "1.007500", "0.995000"),
            ),
        ),
    ),
    BRACKWATER: (
        Terms(
            _grid("1.017500", "1.012500", "1.005000", "0.990000"),
            "base §4.1",
            DayCount.THIRTY_360,
            "base §4.2",
        ),
        (
            _Version(date(2026, 8, 24), "amendment-1", day_count=DayCount.ACTUAL_365),
            _Version(date(2026, 10, 1), "amendment-2", eligible_tiers=frozenset(TIERS[:3])),
        ),
    ),
    TESSALINE: (
        Terms(
            _grid("1.022500", "1.015000", "1.010000", "0.997500"),
            "base §4.1",
            DayCount.ACTUAL_365,
            "base §4.2",
        ),
        (
            _Version(date(2026, 7, 1), "amendment-2", accrual_section="§4.4"),
            _Version(
                date(2026, 8, 24),
                "amendment-1",
                pricing=_grid("1.022500", "1.015000", "1.005000", "0.997500"),
            ),
        ),
    ),
}


def terms_in_force(counterparty_id: str, on: date) -> Terms:
    if on < _BASE_EFFECTIVE:
        raise ValueError(f"no agreement in force on {on}")
    terms, versions = _AGREEMENTS[counterparty_id]
    for version in sorted(versions, key=lambda v: v.effective):
        if version.effective > on:
            break
        if version.pricing is not None:
            terms = replace(
                terms, pricing_grid=version.pricing, pricing_citation=f"{version.label} §4.1"
            )
        if version.day_count is not None:
            terms = replace(
                terms, day_count=version.day_count, accrual_citation=f"{version.label} §4.2"
            )
        if version.accrual_section is not None:
            terms = replace(terms, accrual_citation=f"{version.label} {version.accrual_section}")
        if version.eligible_tiers is not None:
            terms = replace(terms, eligible_tiers=version.eligible_tiers)
    return terms


@dataclass(frozen=True)
class Settlement:
    scheduled_date: date
    """Date from the schedule, before the business day roll."""
    settlement_date: date


_SCHEDULES: dict[str, Callable[[date], bool]] = {
    QUILLMONT: lambda day: day.weekday() == 2,  # weekly, Wednesday
    BRACKWATER: lambda day: day.day == 15 or day == last_business_day_of_month(day.year, day.month),
    TESSALINE: lambda day: day.weekday() == 4,  # weekly, Friday
}


def _scheduled_dates(counterparty_id: str, start: date, end: date) -> Iterator[date]:
    is_scheduled = _SCHEDULES[counterparty_id]
    day = start
    while day <= end:
        if is_scheduled(day):
            yield day
        day += timedelta(days=1)


def settlements(counterparty_id: str, start: date, end: date) -> list[Settlement]:
    """Settlements whose (rolled) settlement date falls inside [start, end]."""
    result: list[Settlement] = []
    for scheduled in _scheduled_dates(counterparty_id, start, end):
        settled = following_business_day(scheduled)
        if settled <= end:
            result.append(Settlement(scheduled, settled))
    return result


def cut_off_date(settlement_date: date) -> date:
    return add_business_days(settlement_date, -2)
