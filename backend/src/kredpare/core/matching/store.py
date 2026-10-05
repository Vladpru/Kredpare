"""Run matching over stored records and persist the breaks it finds."""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date

from sqlalchemy import Engine, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.domain import DomainSpec
from kredpare.core.matching import StoredRecord, detect_breaks
from kredpare.core.tables import Break, Record


@dataclass(frozen=True)
class MatchReport:
    detected: int
    created: dict[str, int] = field(default_factory=dict[str, int])
    """New breaks by type; a break found again for the same as-of date is not created twice."""


def run_matching(
    engine: Engine, spec: DomainSpec, as_of: date, *, actor: str = "matching"
) -> MatchReport:
    with Session(engine) as session:
        records = [
            StoredRecord(
                id=r.id,
                file_id=r.file_id,
                row_number=r.row_number,
                counterparty_id=r.counterparty_id,
                batch_id=r.batch_id,
                record_id=r.record_id,
                schema_name=r.schema_name,
                data=r.data,
            )
            for r in session.scalars(select(Record))
        ]
        result = detect_breaks(spec, records, as_of)

        created: Counter[str] = Counter()
        for found in result.breaks:
            break_id = session.scalar(
                insert(Break)
                .values(
                    id=uuid.uuid4(),
                    key=found.key(as_of),
                    as_of=as_of,
                    break_type=found.break_type,
                    left_schema=found.left_schema,
                    right_schema=found.right_schema,
                    side_schema=found.side_schema,
                    counterparty_id=found.counterparty_id,
                    batch_id=found.batch_id,
                    record_id=found.record_id,
                    field=found.field,
                    left_record_id=found.left_record_id,
                    right_record_id=found.right_record_id,
                    left_value=found.left_value,
                    right_value=found.right_value,
                    delta=found.delta,
                    status="open",
                )
                .on_conflict_do_nothing(index_elements=["key"])
                .returning(Break.id)
            )
            if break_id is None:
                continue
            created[found.break_type] += 1
            record_event(
                session,
                actor,
                "break_detected",
                "break",
                str(break_id),
                {"key": found.key(as_of), "break_type": found.break_type},
            )

        changed: Counter[str] = Counter()
        current = {
            rid: status for rid, status in session.execute(select(Record.id, Record.match_status))
        }
        for record_id, status in result.statuses.items():
            if current.get(record_id) != status:
                session.execute(
                    update(Record).where(Record.id == record_id).values(match_status=status)
                )
                changed[status] += 1
        record_event(
            session,
            actor,
            "matching_run",
            "matching_run",
            as_of.isoformat(),
            {
                "as_of": as_of.isoformat(),
                "records": len(records),
                "detected": len(result.breaks),
                "created": dict(created),
                "status_changes": dict(changed),
            },
        )
        session.commit()
    return MatchReport(detected=len(result.breaks), created=dict(created))
