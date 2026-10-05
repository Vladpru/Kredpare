from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError

from kredpare.core.mapping.config import ColumnMapping, MappingConfig, header_hash
from kredpare.core.mapping.normalize import normalize
from kredpare.core.mapping.transforms import Transform

CONFIG = MappingConfig(
    name="acme invoices v1",
    schema_name="Invoice",
    delimiter=";",
    columns=(
        ColumnMapping(source="INV_NO", target="invoice_no", transform=Transform.TEXT),
        ColumnMapping(source="AMT_CENTS", target="amount", transform=Transform.CENTS_TO_DECIMAL),
        ColumnMapping(source="DUE", target="due", transform=Transform.PARSE_DATE_YMD_COMPACT),
    ),
    batch_id_from_metadata=True,
)


def test_header_hash_identifies_the_exact_header_row() -> None:
    assert CONFIG.header_line == "INV_NO;AMT_CENTS;DUE"
    assert CONFIG.header_hash == header_hash("INV_NO;AMT_CENTS;DUE\n1;2;3\n")
    assert CONFIG.header_hash != header_hash("INV_NO;DUE;AMT_CENTS\n")
    assert CONFIG.header_hash == header_hash("INV_NO;AMT_CENTS;DUE\r\n")


def test_config_rejects_duplicate_sources_or_targets() -> None:
    column = ColumnMapping(source="A", target="a", transform=Transform.TEXT)
    with pytest.raises(ValidationError, match="duplicate"):
        MappingConfig(name="x", schema_name="X", columns=(column, column))


def test_normalize_applies_transforms_and_metadata_batch() -> None:
    result = normalize(CONFIG, "INV_NO;AMT_CENTS;DUE\nI-1;1050;20260902\n", batch_id="b-1")

    assert result.errors == ()
    assert result.rows == (
        (
            1,
            {
                "invoice_no": "I-1",
                "amount": Decimal("10.50"),
                "due": date(2026, 9, 2),
                "batch_id": "b-1",
            },
        ),
    )


def test_normalize_keeps_bad_rows_as_errors_with_row_numbers() -> None:
    content = "INV_NO;AMT_CENTS;DUE\nI-1;1050;20260902\nI-2;10.5;20260902\nI-3;1;2026\n"

    result = normalize(CONFIG, content, batch_id="b-1")

    assert [n for n, _ in result.rows] == [1]
    assert [e.row_number for e in result.errors] == [2, 3]
    assert "AMT_CENTS" in result.errors[0].messages[0]
    assert "cents_to_decimal" in result.errors[0].messages[0]


def test_normalize_handles_quoted_cells_and_empty_files() -> None:
    config = MappingConfig(
        name="q",
        schema_name="Q",
        columns=(ColumnMapping(source="Total", target="total", transform=Transform.PARSE_USD),),
    )

    assert normalize(config, 'Total\n"$1,234.50"\n', batch_id=None).rows == (
        (1, {"total": Decimal("1234.50")}),
    )
    assert normalize(config, "Total\n", batch_id=None).rows == ()


def test_normalize_requires_metadata_batch_when_configured() -> None:
    with pytest.raises(ValueError, match="batch_id"):
        normalize(CONFIG, "INV_NO;AMT_CENTS;DUE\n", batch_id=None)


def test_normalize_rejects_a_different_header() -> None:
    with pytest.raises(ValueError, match="header"):
        normalize(CONFIG, "INV_NO;DUE;AMT_CENTS\n", batch_id="b-1")
