import pytest

from kredpare.core.rules.types import BreakView, Explanation
from kredpare.domains.lending.rules.settlement import SettlementDateRoll
from tests.fake_context import FakeContext, make_break


def _break(seller: str, counterparty: str, field: str = "settlement_date") -> BreakView:
    return make_break("date_mismatch", field=field, left_value=seller, right_value=counterparty)


def _explain(seller: str, counterparty: str, field: str = "settlement_date") -> Explanation | None:
    return SettlementDateRoll().explain(_break(seller, counterparty, field), FakeContext())


@pytest.mark.parametrize(
    ("seller", "counterparty"),
    [
        ("2026-08-31", "2026-08-29"),  # Saturday rolled to Monday
        ("2026-08-31", "2026-08-30"),  # Sunday rolled to Monday
        ("2026-09-08", "2026-09-07"),  # Labor Day rolled to Tuesday
    ],
)
def test_counterparty_kept_the_scheduled_date_it_did_not_roll(
    seller: str, counterparty: str
) -> None:
    found = _explain(seller, counterparty)

    assert found is not None
    assert (found.rule, found.cause) == ("settlement_date_roll", "settlement_date_roll")
    assert (found.wrong_side, found.proposal) == ("counterparty", "email")
    assert found.evidence == {
        "field": "settlement_date",
        "seller_value": seller,
        "counterparty_value": counterparty,
        "scheduled_date": counterparty,
        "rolled_date": seller,
        "side_that_rolled": "seller",
    }


def test_seller_kept_the_scheduled_date_so_the_seller_corrects() -> None:
    found = _explain("2026-08-29", "2026-08-31")

    assert found is not None
    assert (found.wrong_side, found.proposal) == ("seller", "correction")
    assert found.evidence["side_that_rolled"] == "counterparty"


@pytest.mark.parametrize(
    ("seller", "counterparty"),
    [
        ("2026-09-01", "2026-08-29"),  # Tuesday is not the next business day after Saturday
        ("2026-09-08", "2026-09-04"),  # both business days
        ("2026-09-04", "2026-09-04"),  # equal: not a break
        ("2026-08-31", "2026-08-27"),  # the later date is Monday, the earlier a Thursday
        ("2026-08-29", "2026-08-30"),  # both weekend days
    ],
)
def test_other_date_differences_are_not_explained(seller: str, counterparty: str) -> None:
    assert _explain(seller, counterparty) is None


def test_only_the_settlement_date_field_is_explained() -> None:
    assert _explain("2026-08-31", "2026-08-29", field="funding_date") is None


def test_a_break_without_values_is_not_explained() -> None:
    brk = make_break("date_mismatch", field="settlement_date")

    assert SettlementDateRoll().explain(brk, FakeContext()) is None
