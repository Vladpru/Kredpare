"""The recompute rules as cascade rules: they infer the day-count convention from the seller
record and never read an agreement. Loans that need an agreement (an amendment, or two causes
at once) must not be claimed."""

from collections.abc import Callable
from decimal import Decimal
from itertools import product

import pytest

from kredpare.core.rules.types import BreakView, Explanation
from kredpare.domains.lending.pricing import DayCount, Rounding, accrued_interest, purchase_price
from kredpare.domains.lending.rules.amounts import AccrualStartAlternative, RoundingDifference
from kredpare.domains.lending.schemas import FundedLoan
from tests.fake_context import CONFIRMATION, SELLER, FakeContext, make_break, make_record
from tests.test_lending_rules import make_loan

RULES = (RoundingDifference(), AccrualStartAlternative())
A365, T360 = DayCount.ACTUAL_365, DayCount.THIRTY_360


def with_accrued(loan: FundedLoan, accrued: Decimal) -> FundedLoan:
    """The loan as a side computing accrued interest differently would file it."""
    return FundedLoan.model_validate(
        {
            **loan.model_dump(),
            "accrued_interest": accrued,
            "purchase_price": purchase_price(loan.upb, loan.price_pct, accrued),
        }
    )


def accrual(
    loan: FundedLoan,
    convention: DayCount,
    *,
    start: str = "funding",
    rounding: Rounding = Rounding.HALF_UP,
) -> Decimal:
    return accrued_interest(
        loan.upb,
        loan.note_rate,
        loan.funding_date if start == "funding" else loan.cut_off_date,
        loan.settlement_date,
        convention,
        rounding=rounding,
    )


def mismatch(
    seller: FundedLoan, counterparty: FundedLoan, field: str
) -> tuple[BreakView, FakeContext]:
    left = make_record(SELLER, data=seller.model_dump(mode="json"))
    right = make_record(CONFIRMATION, data=counterparty.model_dump(mode="json"))
    brk = make_break(
        "amount_mismatch",
        field=field,
        left=left,
        right=right,
        left_value=str(getattr(seller, field)),
        right_value=str(getattr(counterparty, field)),
    )
    return brk, FakeContext([left, right])


def explained_by(seller: FundedLoan, counterparty: FundedLoan, field: str) -> list[Explanation]:
    brk, context = mismatch(seller, counterparty, field)
    return [found for rule in RULES if (found := rule.explain(brk, context)) is not None]


def loan_where(predicate: Callable[[FundedLoan], bool], convention: DayCount = A365) -> FundedLoan:
    for upb in range(20000, 21000):
        loan = make_loan(upb=f"{upb}.00", convention=convention)
        if predicate(loan):
            return loan
    raise AssertionError("no loan matches")


def truncating(convention: DayCount) -> FundedLoan:
    return loan_where(
        lambda f: accrual(f, convention, rounding=Rounding.TRUNCATE) != f.accrued_interest,
        convention,
    )


@pytest.mark.parametrize(
    ("convention", "field"), list(product(DayCount, ("accrued_interest", "purchase_price")))
)
def test_rounding_difference_is_explained_with_the_convention_of_the_seller(
    convention: DayCount, field: str
) -> None:
    seller = truncating(convention)
    counterparty = with_accrued(seller, accrual(seller, convention, rounding=Rounding.TRUNCATE))

    found = explained_by(seller, counterparty, field)

    assert [e.rule for e in found] == ["rounding_difference"]
    only = found[0]
    assert (only.cause, only.wrong_side, only.proposal) == (
        "rounding_difference",
        "counterparty",
        "email",
    )
    assert only.evidence["day_count"] == convention.value
    assert only.evidence["rounding"] == "truncate"
    assert only.evidence["counterparty_value"] == str(getattr(counterparty, field))
    assert only.evidence["recomputed_value"] == str(getattr(counterparty, field))
    assert only.evidence["seller_value"] == str(getattr(seller, field))


@pytest.mark.parametrize(
    ("convention", "field"), list(product(DayCount, ("accrued_interest", "purchase_price")))
)
def test_accrual_start_alternative_is_explained_with_the_convention_of_the_seller(
    convention: DayCount, field: str
) -> None:
    seller = make_loan(convention=convention)
    counterparty = with_accrued(seller, accrual(seller, convention, start="cut_off"))
    assert counterparty.accrued_interest != seller.accrued_interest

    found = explained_by(seller, counterparty, field)

    assert [e.rule for e in found] == ["accrual_start_alternative"]
    only = found[0]
    assert (only.cause, only.wrong_side, only.proposal) == (
        "accrual_start_alternative",
        "counterparty",
        "email",
    )
    assert only.evidence["day_count"] == convention.value
    assert only.evidence["accrual_start"] == seller.cut_off_date.isoformat()
    assert only.evidence["accrual_end"] == seller.settlement_date.isoformat()


def test_evidence_is_json_safe_with_decimals_as_strings() -> None:
    seller = truncating(A365)
    counterparty = with_accrued(seller, accrual(seller, A365, rounding=Rounding.TRUNCATE))

    (found,) = explained_by(seller, counterparty, "accrued_interest")

    for key in ("upb", "note_rate", "price_pct", "recomputed_accrued_interest"):
        assert isinstance(found.evidence[key], str)
    assert isinstance(found.evidence["accrual_start"], str)


def test_a_seller_value_no_convention_reproduces_is_not_explained() -> None:
    real = truncating(A365)
    odd = with_accrued(real, real.accrued_interest + Decimal("1.00"))
    counterparty = with_accrued(real, accrual(real, A365, rounding=Rounding.TRUNCATE))

    assert explained_by(odd, counterparty, "accrued_interest") == []


def test_combined_causes_old_convention_and_truncation_is_not_claimed() -> None:
    # Seller follows the amended convention (Actual/365); the counterparty still uses 30/360
    # and also truncates. Neither cause alone reproduces its value.
    seller = loan_where(
        lambda f: (
            accrual(f, T360, rounding=Rounding.TRUNCATE)
            not in {
                f.accrued_interest,
                accrual(f, T360),
                accrual(f, A365, rounding=Rounding.TRUNCATE),
            }
        )
    )
    combined = with_accrued(seller, accrual(seller, T360, rounding=Rounding.TRUNCATE))

    for field in ("accrued_interest", "purchase_price"):
        assert explained_by(seller, combined, field) == []


def test_amendment_error_counterparty_on_the_old_convention_is_not_claimed() -> None:
    seller = loan_where(lambda f: accrual(f, T360) != f.accrued_interest)
    counterparty = with_accrued(seller, accrual(seller, T360))

    for field in ("accrued_interest", "purchase_price"):
        assert explained_by(seller, counterparty, field) == []


def test_amendment_error_seller_on_the_old_convention_is_not_claimed() -> None:
    # The seller kept 30/360; the counterparty applies the amended Actual/365.
    base = loan_where(lambda f: accrual(f, T360) != accrual(f, A365))
    seller = with_accrued(base, accrual(base, T360))
    counterparty = with_accrued(base, accrual(base, A365))
    assert counterparty.accrued_interest != accrual(seller, T360, rounding=Rounding.TRUNCATE)
    assert counterparty.accrued_interest != accrual(seller, T360, start="cut_off")

    for field in ("accrued_interest", "purchase_price"):
        assert explained_by(seller, counterparty, field) == []


@pytest.mark.parametrize("field", ["price_pct", "upb", "settlement_date"])
def test_other_fields_are_not_explained(field: str) -> None:
    seller = truncating(A365)
    counterparty = with_accrued(seller, accrual(seller, A365, rounding=Rounding.TRUNCATE))
    brk, context = mismatch(seller, counterparty, "accrued_interest")
    other = make_break(
        "amount_mismatch",
        field=field,
        left=context.record(brk.left_record_id),
        right=context.record(brk.right_record_id),
        left_value="1",
        right_value="2",
    )

    assert all(rule.explain(other, context) is None for rule in RULES)


def test_a_break_without_both_records_is_not_explained() -> None:
    seller = truncating(A365)
    counterparty = with_accrued(seller, accrual(seller, A365, rounding=Rounding.TRUNCATE))
    brk, context = mismatch(seller, counterparty, "accrued_interest")
    lonely = make_break(
        "amount_mismatch",
        field="accrued_interest",
        left=context.record(brk.left_record_id),
        left_value=brk.left_value,
        right_value=brk.right_value,
    )

    assert all(rule.explain(lonely, context) is None for rule in RULES)


def test_a_break_whose_seller_value_differs_from_the_seller_record_is_not_explained() -> None:
    seller = truncating(A365)
    counterparty = with_accrued(seller, accrual(seller, A365, rounding=Rounding.TRUNCATE))
    brk, context = mismatch(seller, counterparty, "accrued_interest")
    stale = make_break(
        "amount_mismatch",
        field="accrued_interest",
        left=context.record(brk.left_record_id),
        right=context.record(brk.right_record_id),
        left_value="0.01",
        right_value=brk.right_value,
    )

    assert all(rule.explain(stale, context) is None for rule in RULES)
