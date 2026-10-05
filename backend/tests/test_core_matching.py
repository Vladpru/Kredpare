import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ConfigDict

from kredpare.core.canonical import Money
from kredpare.core.domain import BreakType, DomainSpec, MatchDeclaration, SchemaSpec
from kredpare.core.matching import StoredRecord, detect_breaks

AS_OF = date(2026, 9, 18)  # a Friday


class Invoice(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    invoice_no: str
    batch_id: str
    amount: Money
    due: date
    issued: date


class Payment(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")
    invoice_no: str
    batch_id: str
    amount: Money
    due: date


class Weekdays:
    def add_business_days(self, day: date, count: int) -> date:
        while count:
            day += timedelta(days=1)
            if day.weekday() < 5:
                count -= 1
        return day


SPEC = DomainSpec(
    name="billing",
    schemas=(
        SchemaSpec(Invoice, record_id_field="invoice_no"),
        SchemaSpec(Payment, record_id_field="invoice_no"),
    ),
    break_types=(BreakType("missing_record", "x"),),
    match_declarations=(
        MatchDeclaration(
            left="Invoice",
            right="Payment",
            key_fields=("counterparty_id", "batch_id", "invoice_no"),
            money_fields=("amount",),
            date_fields=("due",),
            delivery_fields=("counterparty_id", "batch_id"),
            age_from="issued",
        ),
    ),
    calendar=Weekdays(),
    stale_after_business_days=5,
)

INVOICE_FILE, PAYMENT_FILE, OTHER_FILE = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()


def _invoice(
    no: str,
    *,
    amount: str = "10.50",
    issued: date = date(2026, 9, 14),
    batch: str = "b-1",
    counterparty: str = "cp-a",
    file_id: uuid.UUID = INVOICE_FILE,
    row: int = 1,
) -> StoredRecord:
    return StoredRecord(
        id=uuid.uuid4(),
        file_id=file_id,
        row_number=row,
        counterparty_id=counterparty,
        batch_id=batch,
        record_id=no,
        schema_name="Invoice",
        data={
            "invoice_no": no,
            "batch_id": batch,
            "amount": amount,
            "due": "2026-10-01",
            "issued": issued.isoformat(),
        },
    )


def _payment(
    no: str,
    *,
    amount: str = "10.50",
    due: str = "2026-10-01",
    batch: str = "b-1",
    counterparty: str = "cp-a",
    file_id: uuid.UUID = PAYMENT_FILE,
    row: int = 1,
) -> StoredRecord:
    return StoredRecord(
        id=uuid.uuid4(),
        file_id=file_id,
        row_number=row,
        counterparty_id=counterparty,
        batch_id=batch,
        record_id=no,
        schema_name="Payment",
        data={"invoice_no": no, "batch_id": batch, "amount": amount, "due": due},
    )


def _types(result: object) -> list[tuple[str, str, str | None, str | None]]:
    return sorted(
        (b.break_type, b.record_id, b.field, b.side_schema)
        for b in result.breaks  # type: ignore[attr-defined]
    )


def test_clean_pair_has_no_breaks_and_is_matched() -> None:
    invoice, payment = _invoice("I-1"), _payment("I-1")

    result = detect_breaks(SPEC, [invoice, payment], AS_OF)

    assert result.breaks == ()
    assert result.statuses == {invoice.id: "matched", payment.id: "matched"}


def test_amount_mismatch_carries_both_values_and_delta() -> None:
    invoice, payment = _invoice("I-1", amount="10.50"), _payment("I-1", amount="10.49")

    (found,) = detect_breaks(SPEC, [invoice, payment], AS_OF).breaks

    assert (found.break_type, found.field) == ("amount_mismatch", "amount")
    assert (found.left_value, found.right_value, found.delta) == (
        "10.50",
        "10.49",
        Decimal("-0.01"),
    )
    assert (found.left_record_id, found.right_record_id) == (invoice.id, payment.id)


def test_amounts_compare_as_decimals_not_text() -> None:
    result = detect_breaks(
        SPEC, [_invoice("I-1", amount="10.50"), _payment("I-1", amount="10.5")], AS_OF
    )

    assert result.breaks == ()


def test_date_mismatch() -> None:
    result = detect_breaks(SPEC, [_invoice("I-1"), _payment("I-1", due="2026-09-30")], AS_OF)

    assert _types(result) == [("date_mismatch", "I-1", "due", None)]


def test_missing_on_the_right_when_that_batch_was_delivered() -> None:
    result = detect_breaks(SPEC, [_invoice("I-1"), _invoice("I-2", row=2), _payment("I-1")], AS_OF)

    assert _types(result) == [("missing_record", "I-2", None, "Payment")]


def test_missing_on_the_left() -> None:
    result = detect_breaks(SPEC, [_invoice("I-1"), _payment("I-1"), _payment("I-9", row=2)], AS_OF)

    assert _types(result) == [("missing_record", "I-9", None, "Invoice")]


def test_undelivered_batch_is_pending_until_stale() -> None:
    young = _invoice("I-1", issued=date(2026, 9, 11))  # +5 business days = 09-18
    old = _invoice("I-2", issued=date(2026, 9, 10), row=2)  # +5 business days = 09-17

    result = detect_breaks(SPEC, [young, old], AS_OF)

    assert _types(result) == [("stale_pending", "I-2", None, "Payment")]
    assert result.statuses[young.id] == "unmatched"
    assert result.statuses[old.id] == "in_break"


def test_duplicate_is_within_one_file_only() -> None:
    first, second = _payment("I-1", row=1), _payment("I-1", row=2)
    elsewhere = _invoice("I-1", file_id=OTHER_FILE)

    result = detect_breaks(SPEC, [_invoice("I-1"), elsewhere, first, second], AS_OF)

    # The same invoice in two different files is not a duplicate.
    assert _types(result) == [("duplicate", "I-1", None, "Payment")]
    assert result.statuses[second.id] == "in_break"


def test_duplicates_are_compared_once() -> None:
    result = detect_breaks(
        SPEC,
        [
            _invoice("I-1"),
            _payment("I-1", amount="9.00", row=1),
            _payment("I-1", amount="9.00", row=2),
        ],
        AS_OF,
    )

    assert _types(result) == [
        ("amount_mismatch", "I-1", "amount", None),
        ("duplicate", "I-1", None, "Payment"),
    ]


def test_counterparty_is_part_of_the_key() -> None:
    result = detect_breaks(
        SPEC, [_invoice("I-1"), _payment("I-1", counterparty="cp-b"), _payment("I-2")], AS_OF
    )

    assert ("missing_record", "I-1", None, "Payment") in _types(result)
    assert ("missing_record", "I-1", None, "Invoice") in _types(result)


@pytest.mark.parametrize("bad", [{"age_from": "nope"}, {"delivery_fields": ("nope",)}])
def test_declaration_age_and_delivery_fields_are_checked(bad: dict[str, object]) -> None:
    declaration = MatchDeclaration(
        left="Invoice",
        right="Payment",
        key_fields=("invoice_no",),
        money_fields=(),
        date_fields=(),
        **bad,  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="nope"):
        DomainSpec(
            name="x",
            schemas=SPEC.schemas,
            break_types=(),
            match_declarations=(declaration,),
            calendar=Weekdays(),
        )


def test_age_from_needs_a_calendar() -> None:
    with pytest.raises(ValueError, match="calendar"):
        DomainSpec(
            name="x",
            schemas=SPEC.schemas,
            break_types=(),
            match_declarations=SPEC.match_declarations,
        )
