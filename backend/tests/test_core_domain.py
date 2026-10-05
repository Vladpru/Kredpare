from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pandera.errors
import polars as pl
import pytest
from pydantic import BaseModel, ConfigDict

from kredpare.core.canonical import Money
from kredpare.core.domain import BreakType, DomainSpec, MatchDeclaration, SchemaSpec


class Invoice(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    invoice_no: str
    batch_id: str
    amount: Money
    due: date


class Payment(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True, extra="forbid")

    invoice_no: str
    batch_id: str
    amount: Money
    due: date


@dataclass(frozen=True)
class _Named:
    name: str


INVOICE = SchemaSpec(Invoice, record_id_field="invoice_no")
PAYMENT = SchemaSpec(Payment, record_id_field="invoice_no")
PAIR = MatchDeclaration(
    left="Invoice",
    right="Payment",
    key_fields=("counterparty_id", "batch_id", "invoice_no"),
    money_fields=("amount",),
    date_fields=("due",),
)


def _spec(**overrides: object) -> DomainSpec:
    fields: dict[str, object] = {
        "name": "billing",
        "schemas": (INVOICE, PAYMENT),
        "break_types": (BreakType("missing_record", "One side only."),),
        "match_declarations": (PAIR,),
    }
    fields.update(overrides)
    return DomainSpec(**fields)  # pyright: ignore[reportArgumentType]


def test_schema_spec_is_named_after_its_row_model() -> None:
    assert INVOICE.name == "Invoice"


def test_schema_spec_rejects_unknown_record_id_field() -> None:
    with pytest.raises(ValueError, match="number"):
        SchemaSpec(Invoice, record_id_field="number")


def test_domain_spec_looks_up_schemas_by_name() -> None:
    assert _spec().schema("Payment") is PAYMENT


def test_domain_spec_rules_and_tools_default_to_empty() -> None:
    spec = _spec()

    assert spec.rules == ()
    assert spec.tools == ()


def test_domain_spec_registers_rules_and_tools_by_name() -> None:
    spec = _spec(rules=(_Named("r1"),), tools=(_Named("t1"),))

    assert [r.name for r in spec.rules] == ["r1"]
    assert [t.name for t in spec.tools] == ["t1"]


def test_domain_spec_rejects_duplicate_schema_names() -> None:
    with pytest.raises(ValueError, match="Invoice"):
        _spec(schemas=(INVOICE, INVOICE))


def test_domain_spec_rejects_duplicate_break_types() -> None:
    dup = BreakType("missing_record", "again")
    with pytest.raises(ValueError, match="missing_record"):
        _spec(break_types=(dup, dup))


def test_match_declaration_must_reference_registered_schemas() -> None:
    with pytest.raises(ValueError, match="Refund"):
        _spec(match_declarations=(MatchDeclaration("Invoice", "Refund", ("invoice_no",), (), ()),))


@pytest.mark.parametrize(
    "declaration",
    [
        MatchDeclaration("Invoice", "Payment", ("invoice_no", "missing_key"), (), ()),
        MatchDeclaration("Invoice", "Payment", ("invoice_no",), ("missing_money",), ()),
        MatchDeclaration("Invoice", "Payment", ("invoice_no",), (), ("missing_date",)),
    ],
)
def test_match_declaration_fields_must_exist_on_both_sides(declaration: MatchDeclaration) -> None:
    with pytest.raises(ValueError, match="missing_"):
        _spec(match_declarations=(declaration,))


def test_envelope_fields_are_valid_match_keys() -> None:
    # counterparty_id lives on CanonicalRecord, not on the row model.
    assert _spec().match_declarations == (PAIR,)


def _invoice_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "invoice_no": "I-1",
        "batch_id": "b-1",
        "amount": Decimal("10.50"),
        "due": date(2026, 9, 2),
    }
    row.update(overrides)
    return row


def _invoice_frame(**overrides: object) -> pl.DataFrame:
    return pl.DataFrame([_invoice_row(**overrides)])


def test_validate_frame_returns_typed_rows() -> None:
    result = INVOICE.validate_frame(_invoice_frame())

    assert result.errors == ()
    assert result.rows == (
        Invoice(invoice_no="I-1", batch_id="b-1", amount=Decimal("10.50"), due=date(2026, 9, 2)),
    )


def test_validate_frame_reports_invalid_rows_with_row_numbers() -> None:
    good = _invoice_row()
    bad = _invoice_row(invoice_no="I-2", amount=Decimal("10.505"))
    result = INVOICE.validate_frame(pl.DataFrame([good, bad]))

    assert [r.model_dump()["invoice_no"] for r in result.rows] == ["I-1"]
    assert [e.row_number for e in result.errors] == [2]
    assert "amount" in result.errors[0].messages[0]
    assert "2 decimal places" in result.errors[0].messages[0]


def test_validate_frame_rejects_extra_columns() -> None:
    with pytest.raises(pandera.errors.SchemaErrors, match="note"):
        INVOICE.validate_frame(_invoice_frame(note="x"))


def test_validate_frame_rejects_missing_columns() -> None:
    with pytest.raises(pandera.errors.SchemaErrors, match="due"):
        INVOICE.validate_frame(_invoice_frame().drop("due"))


def test_validate_frame_rejects_nulls() -> None:
    with pytest.raises(pandera.errors.SchemaErrors, match="invoice_no"):
        INVOICE.validate_frame(_invoice_frame(invoice_no=None))
