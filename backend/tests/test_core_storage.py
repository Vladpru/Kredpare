import pytest
from sqlalchemy import Engine, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.tables import AuditEvent, Counterparty

TABLES = {
    "counterparties",
    "mapping_configs",
    "files",
    "records",
    "row_errors",
    "breaks",
    "explanations",
    "audit_events",
}


def test_migration_creates_the_tables(engine: Engine) -> None:
    assert set(inspect(engine).get_table_names()) >= TABLES


def test_money_columns_are_numeric_with_scale(engine: Engine) -> None:
    delta = next(c for c in inspect(engine).get_columns("breaks") if c["name"] == "delta")

    assert str(delta["type"]) == "NUMERIC(20, 6)"


def test_audit_event_is_written_in_the_same_transaction(engine: Engine) -> None:
    with Session(engine) as session:
        session.add(Counterparty(id="cp-x"))
        record_event(session, "test", "counterparty_created", "counterparty", "cp-x", {"a": 1})
        session.rollback()
    with Session(engine) as session:
        assert session.scalars(select(AuditEvent)).all() == []

    with Session(engine) as session:
        record_event(session, "test", "counterparty_created", "counterparty", "cp-x", {"a": 1})
        session.commit()
        event = session.scalars(select(AuditEvent)).one()
        assert (event.actor, event.action, event.entity_id, event.payload) == (
            "test",
            "counterparty_created",
            "cp-x",
            {"a": 1},
        )


@pytest.mark.parametrize(
    "statement",
    [
        "UPDATE audit_events SET action = 'tampered'",
        "DELETE FROM audit_events",
        "TRUNCATE audit_events",
    ],
)
def test_audit_events_are_append_only(engine: Engine, statement: str) -> None:
    with Session(engine) as session:
        record_event(session, "test", "something", "thing", "1", {})
        session.commit()

    with engine.connect() as conn, pytest.raises(DBAPIError, match="append-only"):
        conn.execute(text(statement))

    with Session(engine) as session:
        assert session.scalars(select(AuditEvent.action)).all() == ["something"]
