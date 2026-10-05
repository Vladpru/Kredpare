"""Source value → canonical value. A fixed enum: mappings choose, never define, transforms.

Transforms never round. A value with too many decimals passes through unchanged and the
canonical type (Money, Ratio) rejects it, so the row is stored as a validation error.
"""

import re
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from enum import StrEnum

_DECIMAL = re.compile(r"-?\d+(\.\d+)?")
_INTEGER = re.compile(r"-?\d+")
_USD = re.compile(r"(-?)\$(\d{1,3}(,\d{3})*|\d+)(\.\d+)?")
_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_DMON_Y = re.compile(r"(\d{2})-([A-Z][a-z]{2})-(\d{4})")


class TransformError(ValueError):
    pass


class Transform(StrEnum):
    TEXT = "text"
    PARSE_INT = "parse_int"
    PARSE_DECIMAL = "parse_decimal"
    PARSE_USD = "parse_usd"
    CENTS_TO_DECIMAL = "cents_to_decimal"
    PERCENT_TO_FRACTION = "percent_to_fraction"
    PARSE_DATE_ISO = "parse_date_iso"
    PARSE_DATE_MDY = "parse_date_mdy"
    PARSE_DATE_YMD_COMPACT = "parse_date_ymd_compact"
    PARSE_DATE_DMON_Y = "parse_date_dmon_y"


def _decimal(text: str) -> Decimal:
    if not _DECIMAL.fullmatch(text):
        raise ValueError("not a plain decimal")
    try:
        return Decimal(text)
    except InvalidOperation as exc:  # pragma: no cover - the regex already guards this
        raise ValueError("not a decimal") from exc


def _int(text: str) -> int:
    if not _INTEGER.fullmatch(text):
        raise ValueError("not an integer")
    return int(text)


def _usd(text: str) -> Decimal:
    match = _USD.fullmatch(text)
    if not match:
        raise ValueError("not a $1,234.50 amount")
    sign, whole, _, fraction = match.groups()
    return Decimal(f"{sign}{whole.replace(',', '')}{fraction or ''}")


def _strict_date(text: str, pattern: str, fmt: str) -> date:
    if not re.fullmatch(pattern, text):
        raise ValueError(f"not {fmt}")
    return datetime.strptime(text, fmt).date()


def _dmon_y(text: str) -> date:
    match = _DMON_Y.fullmatch(text)
    if not match or match.group(2) not in _MONTHS:
        raise ValueError("not DD-Mon-YYYY")
    day, month, year = match.groups()
    return date(int(year), _MONTHS.index(month) + 1, int(day))


_FUNCTIONS: dict[Transform, Callable[[str], object]] = {
    Transform.TEXT: lambda text: text,
    Transform.PARSE_INT: _int,
    Transform.PARSE_DECIMAL: _decimal,
    Transform.PARSE_USD: _usd,
    Transform.CENTS_TO_DECIMAL: lambda text: Decimal(_int(text)).scaleb(-2),
    Transform.PERCENT_TO_FRACTION: lambda text: _decimal(text).scaleb(-2),
    Transform.PARSE_DATE_ISO: lambda text: _strict_date(text, r"\d{4}-\d{2}-\d{2}", "%Y-%m-%d"),
    Transform.PARSE_DATE_MDY: lambda text: _strict_date(text, r"\d{2}/\d{2}/\d{4}", "%m/%d/%Y"),
    Transform.PARSE_DATE_YMD_COMPACT: lambda text: _strict_date(text, r"\d{8}", "%Y%m%d"),
    Transform.PARSE_DATE_DMON_Y: _dmon_y,
}


def apply(transform: Transform, raw: str) -> object:
    text = raw.strip()
    if not text:
        raise TransformError(f"{transform.value}: empty cell")
    try:
        return _FUNCTIONS[transform](text)
    except ValueError as exc:
        raise TransformError(f"{transform.value}: {raw!r} {exc}") from None
