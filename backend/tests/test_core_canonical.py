from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from kredpare.core.canonical import (
    CanonicalRecord,
    MatchStatus,
    Money,
    Ratio,
    round_half_up_cents,
)


class _Amounts(BaseModel):
    model_config = ConfigDict(strict=True)

    money: Money
    ratio: Ratio


def test_money_and_ratio_normalize_to_fixed_places() -> None:
    row = _Amounts(money=Decimal("20365.7"), ratio=Decimal("0.0999"))

    assert str(row.money) == "20365.70"
    assert str(row.ratio) == "0.099900"


def test_trailing_zeros_beyond_the_scale_are_not_rounding() -> None:
    row = _Amounts(money=Decimal("1.230"), ratio=Decimal("1.0150000"))

    assert str(row.money) == "1.23"
    assert str(row.ratio) == "1.015000"


@pytest.mark.parametrize("money", [Decimal("1.234"), Decimal("0.005")])
def test_money_with_more_than_two_decimals_is_rejected_not_rounded(money: Decimal) -> None:
    with pytest.raises(ValidationError, match="2 decimal places"):
        _Amounts(money=money, ratio=Decimal("1"))


def test_ratio_with_more_than_six_decimals_is_rejected() -> None:
    with pytest.raises(ValidationError, match="6 decimal places"):
        _Amounts(money=Decimal("1"), ratio=Decimal("0.0999001"))


@pytest.mark.parametrize("value", [1.5, 1, "1.50"])
def test_money_accepts_only_decimal(value: object) -> None:
    with pytest.raises(ValidationError):
        _Amounts(money=value, ratio=Decimal("1"))  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_money_rejects_non_finite(value: Decimal) -> None:
    with pytest.raises(ValidationError, match="finite"):
        _Amounts(money=value, ratio=Decimal("1"))


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (Decimal("2.005"), Decimal("2.01")),
        (Decimal("2.004999"), Decimal("2.00")),
        (Decimal("-2.005"), Decimal("-2.01")),
        (Decimal("20300.00") * Decimal("1.015000"), Decimal("20604.50")),
    ],
)
def test_round_half_up_cents(value: Decimal, expected: Decimal) -> None:
    result = round_half_up_cents(value)

    assert result == expected
    assert result.as_tuple().exponent == -2


def _record(**overrides: object) -> CanonicalRecord:
    fields: dict[str, object] = {
        "record_id": "R-1",
        "counterparty_id": "cp-x",
        "batch_id": "cp-x-2026-09-02",
        "file_id": uuid4(),
        "row_number": 1,
        "schema_name": "SomeSchema",
    }
    fields.update(overrides)
    return CanonicalRecord.model_validate(fields)


def test_canonical_record_starts_unmatched() -> None:
    assert _record().match_status is MatchStatus.UNMATCHED


def test_match_status_values() -> None:
    assert [s.value for s in MatchStatus] == ["unmatched", "matched", "in_break"]


def test_canonical_record_trims_ids_and_keeps_case() -> None:
    record = _record(record_id="  L-00451a ")

    assert record.record_id == "L-00451a"


@pytest.mark.parametrize("field", ["record_id", "counterparty_id", "batch_id", "schema_name"])
def test_canonical_record_rejects_blank_ids(field: str) -> None:
    with pytest.raises(ValidationError):
        _record(**{field: "  "})


def test_canonical_record_row_numbers_start_at_one() -> None:
    with pytest.raises(ValidationError):
        _record(row_number=0)


def test_canonical_record_is_immutable() -> None:
    record = _record()

    with pytest.raises(ValidationError):
        record.record_id = "other"  # pyright: ignore[reportAttributeAccessIssue]


def test_canonical_record_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        _record(settled_on=date(2026, 9, 2))
