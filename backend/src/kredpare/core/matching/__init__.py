"""Matching engine: records in, typed breaks out. It never decides a cause.

Keys, compared fields, delivery, and ageing come from the domain's MatchDeclarations.
DuckDB does the set work (first row per key, pairs, one-sided keys, duplicates); values are
compared in Python as Decimal, so nothing is rounded or compared as text.
"""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Literal

import duckdb

from kredpare.core.domain import DomainSpec, MatchDeclaration

BreakType = Literal[
    "missing_record", "duplicate", "amount_mismatch", "date_mismatch", "stale_pending"
]
MatchStatus = Literal["unmatched", "matched", "in_break"]

_ENVELOPE = ("rid", "file_id", "row_number", "counterparty_id", "batch_id", "record_id")


@dataclass(frozen=True)
class StoredRecord:
    id: uuid.UUID
    file_id: uuid.UUID
    row_number: int
    counterparty_id: str
    batch_id: str
    record_id: str
    schema_name: str
    data: Mapping[str, object]
    """Canonical values in JSON form: decimals as exact strings, ISO dates."""


@dataclass(frozen=True)
class DetectedBreak:
    break_type: BreakType
    left_schema: str
    right_schema: str | None
    side_schema: str | None
    counterparty_id: str
    batch_id: str
    record_id: str
    field: str | None = None
    left_record_id: uuid.UUID | None = None
    right_record_id: uuid.UUID | None = None
    left_value: str | None = None
    right_value: str | None = None
    delta: Decimal | None = None

    def key(self, as_of: date) -> str:
        """Natural key: the same break found again for the same as-of date is the same break."""
        return "|".join(
            str(part or "")
            for part in (
                as_of.isoformat(),
                self.break_type,
                self.left_schema,
                self.right_schema,
                self.side_schema,
                self.counterparty_id,
                self.batch_id,
                self.record_id,
                self.field,
            )
        )


@dataclass(frozen=True)
class MatchResult:
    breaks: tuple[DetectedBreak, ...]
    statuses: dict[uuid.UUID, MatchStatus]


def detect_breaks(spec: DomainSpec, records: Sequence[StoredRecord], as_of: date) -> MatchResult:
    by_schema: dict[str, list[StoredRecord]] = {s.name: [] for s in spec.schemas}
    for record in records:
        by_schema[record.schema_name].append(record)
    rows = {r.id: _row(r) for r in records}
    statuses: dict[uuid.UUID, MatchStatus] = {r.id: "unmatched" for r in records}
    breaks: list[DetectedBreak] = []

    con = duckdb.connect()
    try:
        for schema in spec.schemas:
            _register(con, schema.name, schema.field_names, by_schema[schema.name])
        for schema in spec.schemas:
            breaks += _duplicates(con, schema.name, rows, statuses)
        for declaration in spec.match_declarations:
            breaks += _match(con, spec, declaration, rows, statuses, as_of)
    finally:
        con.close()
    return MatchResult(tuple(breaks), statuses)


def _row(record: StoredRecord) -> dict[str, object]:
    """Data fields plus the envelope; envelope values win on a name clash."""
    return {
        **record.data,
        "rid": record.id,
        "file_id": record.file_id,
        "row_number": record.row_number,
        "counterparty_id": record.counterparty_id,
        "batch_id": record.batch_id,
        "record_id": record.record_id,
    }


def _register(
    con: duckdb.DuckDBPyConnection,
    name: str,
    field_names: frozenset[str],
    records: Sequence[StoredRecord],
) -> None:
    """One VARCHAR column per field, so DuckDB never converts a value."""
    columns = list(_ENVELOPE) + sorted(field_names - set(_ENVELOPE))
    types = ", ".join(f'"{c}" {"INTEGER" if c == "row_number" else "VARCHAR"}' for c in columns)
    con.execute(f'CREATE TABLE "{name}" ({types})')
    if records:
        placeholders = ", ".join("?" for _ in columns)
        con.executemany(
            f'INSERT INTO "{name}" VALUES ({placeholders})',
            [[_cell(_row(r).get(c), c) for c in columns] for r in records],
        )


def _cell(value: object, column: str) -> object:
    if value is None or column == "row_number":
        return value
    return str(value)


def _quoted(names: Sequence[str]) -> str:
    return ", ".join(f'"{n}"' for n in names)


def _first_per_key(table: str, keys: Sequence[str]) -> str:
    return (
        f'SELECT * FROM "{table}" QUALIFY row_number() OVER '
        f"(PARTITION BY {_quoted(keys)} ORDER BY file_id, row_number) = 1"
    )


def _duplicates(
    con: duckdb.DuckDBPyConnection,
    table: str,
    rows: Mapping[uuid.UUID, Mapping[str, object]],
    statuses: dict[uuid.UUID, MatchStatus],
) -> list[DetectedBreak]:
    """The same record id more than once in one file."""
    found: list[DetectedBreak] = []
    groups = con.execute(
        f'SELECT list(rid ORDER BY row_number) FROM "{table}" '
        "GROUP BY file_id, record_id HAVING count(*) > 1 ORDER BY min(record_id), file_id"
    ).fetchall()
    for (ids,) in groups:
        rids = [uuid.UUID(i) for i in ids]
        first = rows[rids[0]]
        for rid in rids:
            statuses[rid] = "in_break"
        found.append(
            DetectedBreak(
                "duplicate",
                left_schema=table,
                right_schema=None,
                side_schema=table,
                counterparty_id=str(first["counterparty_id"]),
                batch_id=str(first["batch_id"]),
                record_id=str(first["record_id"]),
                left_record_id=rids[0],
            )
        )
    return found


def _match(
    con: duckdb.DuckDBPyConnection,
    spec: DomainSpec,
    declaration: MatchDeclaration,
    rows: Mapping[uuid.UUID, Mapping[str, object]],
    statuses: dict[uuid.UUID, MatchStatus],
    as_of: date,
) -> list[DetectedBreak]:
    keys = declaration.key_fields
    left, right = declaration.left, declaration.right
    con.execute(f"CREATE OR REPLACE TEMP VIEW l AS {_first_per_key(left, keys)}")
    con.execute(f"CREATE OR REPLACE TEMP VIEW r AS {_first_per_key(right, keys)}")
    pairs = con.execute(
        f"SELECT l.rid, r.rid FROM l JOIN r USING ({_quoted(keys)}) ORDER BY l.record_id"
    ).fetchall()
    left_only = con.execute(
        f"SELECT rid FROM l ANTI JOIN r USING ({_quoted(keys)}) ORDER BY record_id"
    ).fetchall()
    right_only = con.execute(
        f"SELECT rid FROM r ANTI JOIN l USING ({_quoted(keys)}) ORDER BY record_id"
    ).fetchall()
    delivered: set[tuple[object, ...]] = set()
    if declaration.delivery_fields is not None:
        delivered = set(
            con.execute(
                f'SELECT DISTINCT {_quoted(declaration.delivery_fields)} FROM "{right}"'
            ).fetchall()
        )

    found: list[DetectedBreak] = []

    def mark(rid: uuid.UUID, status: MatchStatus) -> None:
        if statuses[rid] != "in_break":
            statuses[rid] = status

    for left_id, right_id in pairs:
        lid, rid = uuid.UUID(left_id), uuid.UUID(right_id)
        lrow, rrow = rows[lid], rows[rid]
        differences = [
            _compared(declaration, lrow, rrow, lid, rid, name, money=True)
            for name in declaration.money_fields
            if Decimal(str(lrow[name])) != Decimal(str(rrow[name]))
        ] + [
            _compared(declaration, lrow, rrow, lid, rid, name, money=False)
            for name in declaration.date_fields
            if str(lrow[name]) != str(rrow[name])
        ]
        found += differences
        for record_id in (lid, rid):
            mark(record_id, "in_break" if differences else "matched")

    for (left_id,) in left_only:
        lid = uuid.UUID(left_id)
        lrow = rows[lid]
        if declaration.delivery_fields is not None and (
            tuple(str(lrow[f]) for f in declaration.delivery_fields) in delivered
        ):
            found.append(_one_sided("missing_record", declaration, lrow, lid, missing=right))
            mark(lid, "in_break")
        elif _is_stale(spec, declaration, lrow, as_of):
            found.append(_one_sided("stale_pending", declaration, lrow, lid, missing=right))
            mark(lid, "in_break")

    for (right_id,) in right_only:
        rid = uuid.UUID(right_id)
        found.append(_one_sided("missing_record", declaration, rows[rid], rid, missing=left))
        mark(rid, "in_break")
    return found


def _is_stale(
    spec: DomainSpec, declaration: MatchDeclaration, row: Mapping[str, object], as_of: date
) -> bool:
    if declaration.age_from is None or spec.calendar is None:
        return False
    anchor = date.fromisoformat(str(row[declaration.age_from]))
    return as_of > spec.calendar.add_business_days(anchor, spec.stale_after_business_days)


def _compared(
    declaration: MatchDeclaration,
    lrow: Mapping[str, object],
    rrow: Mapping[str, object],
    lid: uuid.UUID,
    rid: uuid.UUID,
    name: str,
    *,
    money: bool,
) -> DetectedBreak:
    left_value, right_value = str(lrow[name]), str(rrow[name])
    return DetectedBreak(
        "amount_mismatch" if money else "date_mismatch",
        left_schema=declaration.left,
        right_schema=declaration.right,
        side_schema=None,
        counterparty_id=str(lrow["counterparty_id"]),
        batch_id=str(lrow["batch_id"]),
        record_id=str(lrow["record_id"]),
        field=name,
        left_record_id=lid,
        right_record_id=rid,
        left_value=left_value,
        right_value=right_value,
        delta=Decimal(right_value) - Decimal(left_value) if money else None,
    )


def _one_sided(
    break_type: BreakType,
    declaration: MatchDeclaration,
    row: Mapping[str, object],
    record_id: uuid.UUID,
    *,
    missing: str,
) -> DetectedBreak:
    present_on_left = missing == declaration.right
    return DetectedBreak(
        break_type,
        left_schema=declaration.left,
        right_schema=declaration.right,
        side_schema=missing,
        counterparty_id=str(row["counterparty_id"]),
        batch_id=str(row["batch_id"]),
        record_id=str(row["record_id"]),
        left_record_id=record_id if present_on_left else None,
        right_record_id=None if present_on_left else record_id,
    )
