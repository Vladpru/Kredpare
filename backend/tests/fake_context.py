"""In-memory RuleContext and view builders for rule unit tests."""

import uuid
from collections.abc import Iterable, Mapping
from datetime import date

from kredpare.core.rules.types import BreakView, RecordView

BATCH = "cp-quillmont-2026-09-02"
CP = "cp-quillmont"
LOAN = "L-000001"
SELLER = "FundedLoan"
CONFIRMATION = "PurchaseConfirmation"
FILE_A = uuid.UUID(int=1)
FILE_B = uuid.UUID(int=2)


def make_record(
    schema_name: str,
    *,
    loan: str = LOAN,
    batch: str = BATCH,
    counterparty: str = CP,
    file_id: uuid.UUID = FILE_A,
    row_number: int = 1,
    data: Mapping[str, object] | None = None,
) -> RecordView:
    return RecordView(
        id=uuid.uuid4(),
        file_id=file_id,
        row_number=row_number,
        counterparty_id=counterparty,
        batch_id=batch,
        record_id=loan,
        schema_name=schema_name,
        data=data if data is not None else {"loan_id": loan, "batch_id": batch},
    )


def make_break(
    break_type: str,
    *,
    side_schema: str | None = None,
    field: str | None = None,
    left: RecordView | None = None,
    right: RecordView | None = None,
    left_value: str | None = None,
    right_value: str | None = None,
    loan: str = LOAN,
    batch: str = BATCH,
    counterparty: str = CP,
) -> BreakView:
    return BreakView(
        id=uuid.uuid4(),
        as_of=date(2026, 9, 8),
        break_type=break_type,
        left_schema=SELLER,
        right_schema=CONFIRMATION,
        side_schema=side_schema,
        counterparty_id=counterparty,
        batch_id=batch,
        record_id=loan,
        field=field,
        left_record_id=left.id if left else None,
        right_record_id=right.id if right else None,
        left_value=left_value,
        right_value=right_value,
        delta=None,
    )


class FakeContext:
    def __init__(
        self, records: Iterable[RecordView] = (), breaks: Iterable[BreakView] = ()
    ) -> None:
        self.records = list(records)
        self.breaks = list(breaks)

    def record(self, record_pk: uuid.UUID | None) -> RecordView | None:
        return next((r for r in self.records if r.id == record_pk), None)

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
        wanted = {
            "schema_name": schema_name,
            "counterparty_id": counterparty_id,
            "batch_id": batch_id,
            "record_id": record_id,
            "file_id": file_id,
        }
        found = [
            r
            for r in self.records
            if all(v is None or getattr(r, k) == v for k, v in wanted.items())
        ]
        found.sort(key=lambda r: (r.file_id, r.row_number))
        return tuple(found if limit is None else found[:limit])

    def find_breaks(
        self,
        *,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        record_id: str | None = None,
    ) -> tuple[BreakView, ...]:
        wanted = {"counterparty_id": counterparty_id, "batch_id": batch_id, "record_id": record_id}
        return tuple(
            b
            for b in self.breaks
            if all(v is None or getattr(b, k) == v for k, v in wanted.items())
        )
