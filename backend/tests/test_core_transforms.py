from datetime import date
from decimal import Decimal

import pytest

from kredpare.core.mapping.transforms import Transform, TransformError, apply


@pytest.mark.parametrize(
    ("transform", "raw", "expected"),
    [
        (Transform.TEXT, " L-004512 ", "L-004512"),
        (Transform.PARSE_INT, "60", 60),
        (Transform.PARSE_DECIMAL, "20365.70", Decimal("20365.70")),
        (Transform.PARSE_DECIMAL, "-0.01", Decimal("-0.01")),
        (Transform.PARSE_USD, "$1,234.50", Decimal("1234.50")),
        (Transform.PARSE_USD, "$72.23", Decimal("72.23")),
        (Transform.PARSE_USD, "-$1,234.50", Decimal("-1234.50")),
        (Transform.CENTS_TO_DECIMAL, "123450", Decimal("1234.50")),
        (Transform.CENTS_TO_DECIMAL, "7", Decimal("0.07")),
        (Transform.PERCENT_TO_FRACTION, "101.500", Decimal("1.015000")),
        (Transform.PERCENT_TO_FRACTION, "99.75", Decimal("0.9975")),
        (Transform.PARSE_DATE_ISO, "2026-09-02", date(2026, 9, 2)),
        (Transform.PARSE_DATE_MDY, "09/02/2026", date(2026, 9, 2)),
        (Transform.PARSE_DATE_YMD_COMPACT, "20260902", date(2026, 9, 2)),
        (Transform.PARSE_DATE_DMON_Y, "02-Sep-2026", date(2026, 9, 2)),
    ],
)
def test_transforms(transform: Transform, raw: str, expected: object) -> None:
    assert apply(transform, raw) == expected


@pytest.mark.parametrize("transform", list(Transform))
def test_empty_cell_is_an_error(transform: Transform) -> None:
    with pytest.raises(TransformError, match="empty"):
        apply(transform, "  ")


@pytest.mark.parametrize(
    ("transform", "raw"),
    [
        (Transform.PARSE_INT, "60.0"),
        (Transform.PARSE_DECIMAL, "1,234.50"),
        (Transform.PARSE_DECIMAL, "NaN"),
        (Transform.PARSE_DECIMAL, "1e3"),
        (Transform.PARSE_USD, "1234.50"),
        (Transform.PARSE_USD, "$1,23.50"),
        (Transform.CENTS_TO_DECIMAL, "12.5"),  # would need rounding to whole cents
        (Transform.CENTS_TO_DECIMAL, "$12"),
        (Transform.PERCENT_TO_FRACTION, "101.5%"),
        (Transform.PARSE_DATE_ISO, "2026-9-2"),
        (Transform.PARSE_DATE_MDY, "2026-09-02"),
        (Transform.PARSE_DATE_MDY, "13/02/2026"),
        (Transform.PARSE_DATE_YMD_COMPACT, "2026092"),
        (Transform.PARSE_DATE_DMON_Y, "02-sep-2026"),
        (Transform.PARSE_DATE_DMON_Y, "31-Sep-2026"),
    ],
)
def test_malformed_values_are_errors(transform: Transform, raw: str) -> None:
    with pytest.raises(TransformError, match=transform.value):
        apply(transform, raw)


def test_transforms_never_round() -> None:
    # Too many decimals pass through unchanged; the canonical Money type rejects them later.
    assert apply(Transform.PARSE_USD, "$1.234") == Decimal("1.234")
    assert apply(Transform.PERCENT_TO_FRACTION, "101.5255") == Decimal("1.015255")
