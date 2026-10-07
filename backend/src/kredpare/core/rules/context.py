"""Read-only RuleContext over the database."""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from kredpare.core.rules.types import BreakView, RecordView
from kredpare.core.tables import Break, Record


def _record_view(row: Record) -> RecordView:
    return RecordView(
        id=row.id,
        file_id=row.file_id,
        row_number=row.row_number,
        counterparty_id=row.counterparty_id,
        batch_id=row.batch_id,
        record_id=row.record_id,
        schema_name=row.schema_name,
        data=row.data,
    )


def break_view(row: Break) -> BreakView:
    return BreakView(
        id=row.id,
        as_of=row.as_of,
        break_type=row.break_type,
        left_schema=row.left_schema,
        right_schema=row.right_schema,
        side_schema=row.side_schema,
        counterparty_id=row.counterparty_id,
        batch_id=row.batch_id,
        record_id=row.record_id,
        field=row.field,
        left_record_id=row.left_record_id,
        right_record_id=row.right_record_id,
        left_value=row.left_value,
        right_value=row.right_value,
        delta=row.delta,
    )


class SessionRuleContext:
    """Every query is built from fixed columns and bound parameters; callers pass values only."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def record(self, record_pk: uuid.UUID | None) -> RecordView | None:
        if record_pk is None:
            return None
        row = self._session.get(Record, record_pk)
        return None if row is None else _record_view(row)

    def find_records(
        self,
        *,
        schema_name: str | None = None,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        record_id: str | None = None,
        file_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> tuple[RecordView, ...]:
        query = select(Record).order_by(Record.file_id, Record.row_number)
        for column, value in (
            (Record.schema_name, schema_name),
            (Record.counterparty_id, counterparty_id),
            (Record.batch_id, batch_id),
            (Record.record_id, record_id),
            (Record.file_id, file_id),
        ):
            if value is not None:
                query = query.where(column == value)
        if limit is not None:
            query = query.limit(limit)
        return tuple(_record_view(row) for row in self._session.scalars(query))

    def find_breaks(
        self,
        *,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        record_id: str | None = None,
    ) -> tuple[BreakView, ...]:
        query = select(Break).order_by(Break.key)
        for column, value in (
            (Break.counterparty_id, counterparty_id),
            (Break.batch_id, batch_id),
            (Break.record_id, record_id),
        ):
            if value is not None:
                query = query.where(column == value)
        return tuple(break_view(row) for row in self._session.scalars(query))
