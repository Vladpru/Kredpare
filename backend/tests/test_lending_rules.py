from datetime import date
from decimal import Decimal

import pytest

from kredpare.domains.lending.pricing import DayCount, Rounding, accrued_interest, purchase_price
from kredpare.domains.lending.rules import (
    accrual_start_alternative,
    rounding_difference,
)
from kredpare.domains.lending.schemas import FundedLoan

CENT = Decimal("0.01")


def make_loan(
    *,
    upb: str = "20300.00",
    rate: str = "0.099900",
    funding: date = date(2026, 8, 10),
    cut_off: date = date(2026, 8, 20),
    settlement: date = date(2026, 9, 2),
    convention: DayCount = DayCount.ACTUAL_365,
) -> FundedLoan:
    accrued = accrued_interest(Decimal(upb), Decimal(rate), funding, settlement, convention)
    return FundedLoan(
        loan_id="L-000001",
        batch_id=f"quillmont-{settlement.isoformat()}",
        dealer_id="D-0001",
        credit_tier="B",
        funding_date=funding,
        cut_off_date=cut_off,
        settlement_date=settlement,
        funded_amount=Decimal("21000.00"),
        upb=Decimal(upb),
        note_rate=Decimal(rate),
        term_months=48,
        price_pct=Decimal("1.015000"),
        accrued_interest=accrued,
        purchase_price=purchase_price(Decimal(upb), Decimal("1.015000"), accrued),
    )


def truncated(loan: FundedLoan, convention: DayCount) -> Decimal:
    return accrued_interest(
        loan.upb,
        loan.note_rate,
        loan.funding_date,
        loan.settlement_date,
        convention,
        rounding=Rounding.TRUNCATE,
    )


def from_cut_off(loan: FundedLoan, convention: DayCount) -> Decimal:
    return accrued_interest(
        loan.upb, loan.note_rate, loan.cut_off_date, loan.settlement_date, convention
    )


def find_truncating_loan(convention: DayCount) -> FundedLoan:
    for upb in range(20000, 20400):
        loan = make_loan(upb=f"{upb}.00", convention=convention)
        if truncated(loan, convention) != loan.accrued_interest:
            return loan
    raise AssertionError("no loan where truncation differs")


# -- rounding_difference -----------------------------------------------------------------


@pytest.mark.parametrize("convention", list(DayCount))
def test_rounding_explained_on_accrued_interest(convention: DayCount) -> None:
    loan = find_truncating_loan(convention)
    cp = truncated(loan, convention)
    ev = rounding_difference(loan, "accrued_interest", cp, convention)
    assert ev is not None
    assert ev.rule == "rounding_difference"
    assert ev.cause == "rounding_difference"
    assert ev.wrong_side == "counterparty"
    assert ev.proposal == "email"
    assert ev.recomputed_accrued_interest == cp
    assert ev.recomputed_value == cp
    assert ev.rounding is Rounding.TRUNCATE
    assert ev.day_count is convention


def test_rounding_explained_on_purchase_price() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    accrued = truncated(loan, DayCount.ACTUAL_365)
    cp_price = purchase_price(loan.upb, loan.price_pct, accrued)
    ev = rounding_difference(loan, "purchase_price", cp_price, DayCount.ACTUAL_365)
    assert ev is not None
    assert ev.recomputed_value == cp_price
    assert ev.recomputed_accrued_interest == accrued


def test_rounding_off_by_a_cent_the_other_way_is_not_explained() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    cp = truncated(loan, DayCount.ACTUAL_365)
    for wrong in (cp - CENT, cp + CENT):
        assert rounding_difference(loan, "accrued_interest", wrong, DayCount.ACTUAL_365) is None


def test_rounding_delta_above_a_cent_is_not_explained() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    cp = loan.accrued_interest - Decimal("0.02")
    assert rounding_difference(loan, "accrued_interest", cp, DayCount.ACTUAL_365) is None


def test_rounding_equal_values_is_not_a_break() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    assert (
        rounding_difference(loan, "accrued_interest", loan.accrued_interest, DayCount.ACTUAL_365)
        is None
    )


def test_rounding_wrong_field_is_not_explained() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    cp = truncated(loan, DayCount.ACTUAL_365)
    assert rounding_difference(loan, "price_pct", cp, DayCount.ACTUAL_365) is None
    assert rounding_difference(loan, "upb", cp, DayCount.ACTUAL_365) is None


def test_rounding_uses_the_convention_passed_in() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    cp = truncated(loan, DayCount.ACTUAL_365)
    other = DayCount.THIRTY_360
    if truncated(loan, other) != cp:
        assert rounding_difference(loan, "accrued_interest", cp, other) is None


def test_rounding_when_truncation_changes_nothing_is_not_explained() -> None:
    # Find a loan where truncation equals half-up: a one-cent counterparty value is unexplained.
    for upb in range(20000, 20400):
        loan = make_loan(upb=f"{upb}.00")
        if truncated(loan, DayCount.ACTUAL_365) == loan.accrued_interest:
            wrong = loan.accrued_interest - CENT
            assert rounding_difference(loan, "accrued_interest", wrong, DayCount.ACTUAL_365) is None
            return
    raise AssertionError("no such loan")


# -- accrual_start_alternative -----------------------------------------------------------


@pytest.mark.parametrize("convention", list(DayCount))
def test_accrual_start_explained_on_accrued_interest(convention: DayCount) -> None:
    loan = make_loan(convention=convention)
    cp = from_cut_off(loan, convention)
    assert cp != loan.accrued_interest
    ev = accrual_start_alternative(loan, "accrued_interest", cp, convention)
    assert ev is not None
    assert ev.rule == "accrual_start_alternative"
    assert ev.cause == "accrual_start_alternative"
    assert ev.wrong_side == "counterparty"
    assert ev.proposal == "email"
    assert ev.recomputed_value == cp
    assert ev.accrual_start == loan.cut_off_date
    assert ev.rounding is Rounding.HALF_UP
    assert ev.day_count is convention


def test_accrual_start_explained_on_purchase_price() -> None:
    loan = make_loan()
    accrued = from_cut_off(loan, DayCount.ACTUAL_365)
    cp_price = purchase_price(loan.upb, loan.price_pct, accrued)
    ev = accrual_start_alternative(loan, "purchase_price", cp_price, DayCount.ACTUAL_365)
    assert ev is not None
    assert ev.recomputed_value == cp_price
    assert ev.recomputed_accrued_interest == accrued


def test_accrual_start_off_by_a_cent_is_not_explained() -> None:
    loan = make_loan()
    cp = from_cut_off(loan, DayCount.ACTUAL_365)
    for wrong in (cp - CENT, cp + CENT):
        assert (
            accrual_start_alternative(loan, "accrued_interest", wrong, DayCount.ACTUAL_365) is None
        )


def test_accrual_start_funding_equals_cut_off_is_not_explained() -> None:
    loan = make_loan(funding=date(2026, 8, 20), cut_off=date(2026, 8, 20))
    cp = loan.accrued_interest + Decimal("5.00")
    assert accrual_start_alternative(loan, "accrued_interest", cp, DayCount.ACTUAL_365) is None
    assert (
        accrual_start_alternative(
            loan, "accrued_interest", loan.accrued_interest, DayCount.ACTUAL_365
        )
        is None
    )


def test_accrual_start_wrong_field_is_not_explained() -> None:
    loan = make_loan()
    cp = from_cut_off(loan, DayCount.ACTUAL_365)
    assert accrual_start_alternative(loan, "price_pct", cp, DayCount.ACTUAL_365) is None


def test_accrual_start_wrong_convention_is_not_explained() -> None:
    loan = make_loan()
    cp = from_cut_off(loan, DayCount.ACTUAL_365)
    assert from_cut_off(loan, DayCount.THIRTY_360) != cp
    assert accrual_start_alternative(loan, "accrued_interest", cp, DayCount.THIRTY_360) is None


def test_accrual_start_does_not_explain_a_truncation_difference() -> None:
    loan = find_truncating_loan(DayCount.ACTUAL_365)
    cp = truncated(loan, DayCount.ACTUAL_365)
    assert accrual_start_alternative(loan, "accrued_interest", cp, DayCount.ACTUAL_365) is None
