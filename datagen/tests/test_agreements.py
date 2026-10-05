from datetime import date
from decimal import Decimal

from kredpare.domains.lending.pricing import DayCount

from kredpare_datagen.agreements import (
    BRACKWATER,
    BUYERS,
    QUILLMONT,
    TESSALINE,
    cut_off_date,
    settlements,
    terms_in_force,
)


def test_three_buyers() -> None:
    assert BUYERS == ("cp-quillmont", "cp-brackwater", "cp-tessaline")


def test_quillmont_tier_b_price_changes_from_amendment_2() -> None:
    before = terms_in_force(QUILLMONT, date(2026, 8, 26))
    after = terms_in_force(QUILLMONT, date(2026, 9, 2))

    assert before.pricing_grid["B"] == Decimal("1.015000")
    assert before.pricing_citation == "base §4.1"
    assert after.pricing_grid == {
        "A": Decimal("1.020000"),
        "B": Decimal("1.010000"),
        "C": Decimal("1.007500"),
        "D": Decimal("0.995000"),
    }
    assert after.pricing_citation == "amendment-2 §4.1"
    assert after.day_count is DayCount.ACTUAL_365


def test_brackwater_day_count_switches_with_amendment_1() -> None:
    before = terms_in_force(BRACKWATER, date(2026, 8, 17))
    after = terms_in_force(BRACKWATER, date(2026, 8, 31))

    assert (before.day_count, before.accrual_citation) == (DayCount.THIRTY_360, "base §4.2")
    assert (after.day_count, after.accrual_citation) == (DayCount.ACTUAL_365, "amendment-1 §4.2")


def test_brackwater_tier_d_ineligible_only_from_amendment_2() -> None:
    assert terms_in_force(BRACKWATER, date(2026, 9, 30)).eligible_tiers == frozenset("ABCD")
    assert terms_in_force(BRACKWATER, date(2026, 10, 1)).eligible_tiers == frozenset("ABC")


def test_tessaline_applies_amendments_in_effective_order_not_number_order() -> None:
    # Amendment 2 (effective 07-01) renumbers accrued interest to §4.4 before Amendment 1.
    early = terms_in_force(TESSALINE, date(2026, 8, 21))
    late = terms_in_force(TESSALINE, date(2026, 8, 28))

    assert early.pricing_grid["C"] == Decimal("1.010000")
    assert early.accrual_citation == "amendment-2 §4.4"
    assert late.pricing_grid["C"] == Decimal("1.005000")
    assert late.pricing_citation == "amendment-1 §4.1"


def test_settlements_match_the_counterparties_doc() -> None:
    start, end = date(2026, 8, 10), date(2026, 9, 8)

    assert [s.settlement_date for s in settlements(QUILLMONT, start, end)] == [
        date(2026, 8, 12),
        date(2026, 8, 19),
        date(2026, 8, 26),
        date(2026, 9, 2),
    ]
    assert [(s.scheduled_date, s.settlement_date) for s in settlements(BRACKWATER, start, end)] == [
        (date(2026, 8, 15), date(2026, 8, 17)),
        (date(2026, 8, 31), date(2026, 8, 31)),
    ]
    assert [s.settlement_date for s in settlements(TESSALINE, start, end)] == [
        date(2026, 8, 14),
        date(2026, 8, 21),
        date(2026, 8, 28),
        date(2026, 9, 4),
    ]


def test_cut_off_is_two_business_days_before_settlement() -> None:
    assert cut_off_date(date(2026, 9, 2)) == date(2026, 8, 31)
    assert cut_off_date(date(2026, 8, 17)) == date(2026, 8, 13)
