from datetime import date, datetime
from decimal import Decimal

import polars as pl
import pytest
from pydantic import ValidationError

from kredpare.domains.lending.schemas import (
    FundedLoan,
    PurchaseConfirmation,
    ServicerOnboarding,
)
from kredpare.domains.lending.spec import LENDING

# upb 20300.00 x price 1.015000 = 20604.50, plus accrued 72.23.
FUNDED_LOAN: dict[str, object] = {
    "loan_id": "L-004512",
    "batch_id": "cp-quillmont-2026-09-02",
    "dealer_id": "D-0042",
    "credit_tier": "B",
    "funding_date": date(2026, 8, 20),
    "cut_off_date": date(2026, 8, 31),
    "settlement_date": date(2026, 9, 2),
    "funded_amount": Decimal("20300.00"),
    "upb": Decimal("20300.00"),
    "note_rate": Decimal("0.099900"),
    "term_months": 60,
    "price_pct": Decimal("1.015000"),
    "accrued_interest": Decimal("72.23"),
    "purchase_price": Decimal("20676.73"),
}


def _funded(**overrides: object) -> FundedLoan:
    return FundedLoan.model_validate({**FUNDED_LOAN, **overrides})


def test_valid_funded_loan() -> None:
    loan = _funded()

    assert loan.purchase_price == Decimal("20676.73")


@pytest.mark.parametrize("loan_id", ["L-4512", "X-004512", "L-0045120", "l-004512"])
def test_funded_loan_id_format(loan_id: str) -> None:
    with pytest.raises(ValidationError, match="loan_id"):
        _funded(loan_id=loan_id)


@pytest.mark.parametrize("dealer_id", ["D-42", "D-00420", "0042"])
def test_funded_loan_dealer_id_format(dealer_id: str) -> None:
    with pytest.raises(ValidationError, match="dealer_id"):
        _funded(dealer_id=dealer_id)


def test_funded_loan_credit_tier_is_a_to_d() -> None:
    with pytest.raises(ValidationError, match="credit_tier"):
        _funded(credit_tier="E")


@pytest.mark.parametrize("batch_id", ["cp-quillmont-2026-09-09", "2026-09-02", "-2026-09-02"])
def test_funded_loan_batch_id_is_counterparty_and_settlement_date(batch_id: str) -> None:
    with pytest.raises(ValidationError, match="batch_id"):
        _funded(batch_id=batch_id)


def test_funding_date_after_cut_off_is_rejected() -> None:
    with pytest.raises(ValidationError, match="funding_date"):
        _funded(funding_date=date(2026, 9, 1))


def test_cut_off_after_settlement_is_rejected() -> None:
    with pytest.raises(ValidationError, match="cut_off_date"):
        _funded(cut_off_date=date(2026, 9, 3))


def test_dates_may_coincide() -> None:
    day = date(2026, 9, 2)
    accrued = Decimal("0.00")

    loan = _funded(
        funding_date=day,
        cut_off_date=day,
        accrued_interest=accrued,
        purchase_price=Decimal("20604.50"),
    )

    assert loan.funding_date == loan.cut_off_date == loan.settlement_date


@pytest.mark.parametrize("field", ["funded_amount", "upb"])
def test_balances_must_be_positive(field: str) -> None:
    with pytest.raises(ValidationError, match=field):
        _funded(**{field: Decimal("0.00")})


def test_upb_above_funded_amount_is_rejected() -> None:
    with pytest.raises(ValidationError, match="upb"):
        _funded(funded_amount=Decimal("20299.99"))


@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("0.360001"), Decimal("-0.01")])
def test_note_rate_out_of_range(rate: Decimal) -> None:
    with pytest.raises(ValidationError, match="note_rate"):
        _funded(note_rate=rate)


def test_note_rate_upper_bound_is_inclusive() -> None:
    assert _funded(note_rate=Decimal("0.36")).note_rate == Decimal("0.360000")


@pytest.mark.parametrize("term", [11, 85])
def test_term_out_of_range(term: int) -> None:
    with pytest.raises(ValidationError, match="term_months"):
        _funded(term_months=term)


@pytest.mark.parametrize("term", [12, 84])
def test_term_bounds_are_inclusive(term: int) -> None:
    assert _funded(term_months=term).term_months == term


def test_negative_accrued_interest_is_rejected() -> None:
    with pytest.raises(ValidationError, match="accrued_interest"):
        _funded(accrued_interest=Decimal("-0.01"), purchase_price=Decimal("20604.49"))


def test_purchase_price_off_by_a_cent_is_rejected() -> None:
    with pytest.raises(ValidationError, match="purchase_price"):
        _funded(purchase_price=Decimal("20676.74"))


def test_purchase_price_rounds_half_up_not_half_even() -> None:
    # 100.50 x 1.010000 = 101.505 exactly: half-up gives 101.51, half-even 101.50.
    base = {
        "funded_amount": Decimal("100.50"),
        "upb": Decimal("100.50"),
        "price_pct": Decimal("1.010000"),
        "accrued_interest": Decimal("0.00"),
    }

    assert _funded(**base, purchase_price=Decimal("101.51")).purchase_price == Decimal("101.51")
    with pytest.raises(ValidationError, match="purchase_price"):
        _funded(**base, purchase_price=Decimal("101.50"))


def test_funded_loan_rejects_float_money() -> None:
    with pytest.raises(ValidationError, match="upb"):
        _funded(upb=20300.0)


CONFIRMATION: dict[str, object] = {
    "loan_id": "L-004512",
    "batch_id": "cp-quillmont-2026-09-02",
    "settlement_date": date(2026, 9, 2),
    "upb": Decimal("20300.00"),
    "price_pct": Decimal("1.015000"),
    "accrued_interest": Decimal("72.23"),
    "purchase_price": Decimal("20676.73"),
}


def test_valid_purchase_confirmation() -> None:
    assert PurchaseConfirmation.model_validate(CONFIRMATION).upb == Decimal("20300.00")


def test_confirmation_purchase_price_is_not_checked_against_the_formula() -> None:
    # A counterparty computing the price differently is a break, not a validation error.
    row = PurchaseConfirmation.model_validate({**CONFIRMATION, "purchase_price": Decimal("1.00")})

    assert row.purchase_price == Decimal("1.00")


def test_confirmation_upb_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="upb"):
        PurchaseConfirmation.model_validate({**CONFIRMATION, "upb": Decimal("0.00")})


def test_confirmation_accrued_interest_not_negative() -> None:
    with pytest.raises(ValidationError, match="accrued_interest"):
        PurchaseConfirmation.model_validate({**CONFIRMATION, "accrued_interest": Decimal("-1")})


def test_confirmation_has_no_seller_only_fields() -> None:
    with pytest.raises(ValidationError, match="dealer_id"):
        PurchaseConfirmation.model_validate({**CONFIRMATION, "dealer_id": "D-0042"})


ONBOARDING: dict[str, object] = {
    "loan_id": "L-004512",
    "boarded_date": date(2026, 9, 4),
    "upb": Decimal("20300.00"),
    "next_payment_due_date": date(2026, 10, 4),
}


def test_valid_servicer_onboarding() -> None:
    assert ServicerOnboarding.model_validate(ONBOARDING).loan_id == "L-004512"


def test_next_payment_due_must_be_after_boarding() -> None:
    with pytest.raises(ValidationError, match="next_payment_due_date"):
        ServicerOnboarding.model_validate({**ONBOARDING, "next_payment_due_date": date(2026, 9, 4)})


def test_onboarding_upb_must_be_positive() -> None:
    with pytest.raises(ValidationError, match="upb"):
        ServicerOnboarding.model_validate({**ONBOARDING, "upb": Decimal("0.00")})


def test_seller_file_validates_at_file_and_row_level() -> None:
    bad = {**FUNDED_LOAN, "loan_id": "L-000002", "purchase_price": Decimal("1.00")}
    frame = pl.DataFrame([FUNDED_LOAN, bad])

    result = LENDING.schema("FundedLoan").validate_frame(frame)

    assert [r.model_dump()["loan_id"] for r in result.rows] == ["L-004512"]
    assert [e.row_number for e in result.errors] == [2]


def test_dates_reject_datetimes() -> None:
    with pytest.raises(ValidationError, match="boarded_date"):
        ServicerOnboarding.model_validate({**ONBOARDING, "boarded_date": datetime(2026, 9, 4, 13)})
