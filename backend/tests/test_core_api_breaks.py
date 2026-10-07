import uuid
from collections.abc import Iterator
from datetime import date
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kredpare.core.api.app import create_app
from kredpare.core.api.breaks import get_session
from kredpare.core.tables import AuditEvent, Break, Counterparty, ExplanationRow, File, Record

AS_OF = date(2026, 9, 8)


def _record(file_id: uuid.UUID, cp: str, row: int, schema: str, data: dict[str, str]) -> Record:
    return Record(
        id=uuid.uuid4(),
        file_id=file_id,
        row_number=row,
        record_id="L-1",
        counterparty_id=cp,
        batch_id="b1",
        schema_name=schema,
        data=data,
    )


@pytest.fixture
def seeded(engine: Engine) -> dict[str, uuid.UUID]:
    """Three breaks: explained (cp-a), pending (cp-a), explained (cp-b)."""
    ids: dict[str, uuid.UUID] = {}
    with Session(engine) as session:
        session.add_all([Counterparty(id="cp-a"), Counterparty(id="cp-b")])
        session.flush()
        file_id = uuid.uuid4()
        session.add(
            File(
                id=file_id,
                sha256="x",
                source_path="x.csv",
                counterparty_id="cp-a",
                schema_name="s",
                batch_id="b1",
                header_hash="h",
                status="ingested",
            )
        )
        session.flush()
        left = _record(file_id, "cp-a", 1, "seller", {"accrued_interest": "72.230000", "n": "1"})
        right = _record(file_id, "cp-a", 2, "buyer", {"accrued_interest": "72.220000", "n": "1"})
        session.add_all([left, right])
        session.flush()

        def make(name: str, cp: str, kind: str, status: str, with_records: bool) -> Break:
            row = Break(
                id=uuid.uuid4(),
                key=name,
                as_of=AS_OF,
                break_type=kind,
                left_schema="seller",
                right_schema="buyer",
                counterparty_id=cp,
                batch_id="b1",
                record_id="L-1",
                field="accrued_interest",
                left_record_id=left.id if with_records else None,
                right_record_id=right.id if with_records else None,
                left_value="72.230000",
                right_value="72.220000",
                delta=Decimal("-0.010000"),
                status=status,
            )
            ids[name] = row.id
            return row

        breaks = [
            make("b1", "cp-a", "amount_mismatch", "explained", True),
            make("b2", "cp-a", "missing_record", "pending_workflow", False),
            make("b3", "cp-b", "amount_mismatch", "explained", False),
        ]
        session.add_all(breaks)
        session.flush()
        for name in ("b1", "b3"):
            session.add(
                ExplanationRow(
                    id=uuid.uuid4(),
                    break_id=ids[name],
                    level="rule",
                    rule="rounding_difference",
                    cause="rounding_difference",
                    wrong_side="seller",
                    proposal="correction",
                    evidence={"citations": ["Amendment 2 s4.1"], "x": "1.50"},
                )
            )
        session.commit()
    return ids


@pytest.fixture
def client(engine: Engine, seeded: dict[str, uuid.UUID]) -> Iterator[TestClient]:
    app = create_app()

    def session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session
    with TestClient(app) as c:
        yield c


def _keys(client: TestClient, **params: str | int) -> list[str]:
    response = client.get("/breaks", params=params)
    assert response.status_code == 200
    return [item["id"] for item in response.json()["items"]]


def test_list_returns_all_in_stable_order(client: TestClient, seeded: dict[str, uuid.UUID]) -> None:
    body = client.get("/breaks").json()
    assert body["total"] == 3
    assert [i["id"] for i in body["items"]] == [str(seeded[k]) for k in ("b1", "b2", "b3")]
    first = body["items"][0]
    assert first["level"] == "rule"
    assert first["rule"] == "rounding_difference"
    assert first["delta"] == "-0.010000"
    assert body["items"][1]["level"] is None


def test_list_filters(client: TestClient, seeded: dict[str, uuid.UUID]) -> None:
    s = {k: str(v) for k, v in seeded.items()}
    assert _keys(client, counterparty_id="cp-b") == [s["b3"]]
    assert _keys(client, break_type="missing_record") == [s["b2"]]
    assert _keys(client, status="pending_workflow") == [s["b2"]]
    assert _keys(client, level="rule") == [s["b1"], s["b3"]]
    assert _keys(client, level="none") == [s["b2"]]
    assert _keys(client, level="workflow") == []
    assert _keys(client, counterparty_id="cp-a", level="rule") == [s["b1"]]


def test_list_paginates(client: TestClient, seeded: dict[str, uuid.UUID]) -> None:
    page = client.get("/breaks", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3
    assert [i["id"] for i in page["items"]] == [str(seeded["b2"])]
    assert client.get("/breaks", params={"limit": 0}).status_code == 422
    assert client.get("/breaks", params={"offset": -1}).status_code == 422


def test_detail_shows_records_explanation_and_citations(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    body = client.get(f"/breaks/{seeded['b1']}").json()
    assert body["left_record"]["data"]["accrued_interest"] == "72.230000"
    assert body["right_record"]["data"]["accrued_interest"] == "72.220000"
    assert body["left_record"]["schema_name"] == "seller"
    assert body["field"] == "accrued_interest"
    assert body["delta"] == "-0.010000"
    explanation = body["explanation"]
    assert explanation["level"] == "rule"
    assert explanation["rule"] == "rounding_difference"
    assert explanation["wrong_side"] == "seller"
    assert explanation["proposal"] == "correction"
    assert explanation["evidence"]["x"] == "1.50"
    assert explanation["citations"] == [{"citation": "Amendment 2 s4.1", "text": None}]
    assert body["decisions"] == []


def test_detail_without_records_or_explanation(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    body = client.get(f"/breaks/{seeded['b2']}").json()
    assert body["left_record"] is None
    assert body["right_record"] is None
    assert body["explanation"] is None


def test_detail_resolves_clause_text_through_the_injected_resolver(
    engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    def resolver(counterparty_id: str, citation: str) -> str | None:
        return f"{counterparty_id}: clause for {citation}"

    app = create_app(clause_resolver=resolver)

    def session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = session
    with TestClient(app) as c:
        body = c.get(f"/breaks/{seeded['b1']}").json()
    assert body["explanation"]["citations"] == [
        {"citation": "Amendment 2 s4.1", "text": "cp-a: clause for Amendment 2 s4.1"}
    ]


def test_unknown_break_is_404_and_bad_id_is_422(client: TestClient) -> None:
    assert client.get(f"/breaks/{uuid.uuid4()}").status_code == 404
    assert client.get("/breaks/not-a-uuid").status_code == 422
    body = {"decision": "approve", "comment": ""}
    assert client.post(f"/breaks/{uuid.uuid4()}/decision", json=body).status_code == 404


def test_decision_writes_one_audit_row_and_changes_nothing_else(
    client: TestClient, engine: Engine, seeded: dict[str, uuid.UUID]
) -> None:
    with Session(engine) as s:
        before_events = s.scalar(select(func.count()).select_from(AuditEvent))
        before_expl = s.execute(
            select(ExplanationRow.id, ExplanationRow.cause, ExplanationRow.evidence).order_by(
                ExplanationRow.id
            )
        ).all()

    response = client.post(
        f"/breaks/{seeded['b1']}/decision",
        json={"decision": "approve", "comment": "looks right"},
        headers={"X-Reviewer": "ana"},
    )

    assert response.status_code == 201
    out = response.json()
    assert (out["decision"], out["comment"], out["actor"]) == ("approve", "looks right", "ana")
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == (before_events or 0) + 1
        event = s.scalars(select(AuditEvent).order_by(AuditEvent.id.desc())).first()
        assert event is not None
        assert (event.actor, event.entity_type, event.entity_id) == (
            "ana",
            "break",
            str(seeded["b1"]),
        )
        assert event.payload == {"decision": "approve", "comment": "looks right"}
        assert s.get(Break, seeded["b1"]).status == "explained"  # type: ignore[union-attr]
        after_expl = s.execute(
            select(ExplanationRow.id, ExplanationRow.cause, ExplanationRow.evidence).order_by(
                ExplanationRow.id
            )
        ).all()
        assert after_expl == before_expl

    history = client.get(f"/breaks/{seeded['b1']}").json()["decisions"]
    assert [(d["decision"], d["actor"], d["comment"]) for d in history] == [
        ("approve", "ana", "looks right")
    ]


def test_decision_defaults_actor_and_keeps_history_in_order(
    client: TestClient, seeded: dict[str, uuid.UUID]
) -> None:
    url = f"/breaks/{seeded['b1']}/decision"
    client.post(url, json={"decision": "reject", "comment": "no"})
    client.post(url, json={"decision": "approve", "comment": "ok"})
    history = client.get(f"/breaks/{seeded['b1']}").json()["decisions"]
    assert [(d["decision"], d["actor"]) for d in history] == [
        ("reject", "reviewer"),
        ("approve", "reviewer"),
    ]


@pytest.mark.parametrize(
    "body",
    [
        {"decision": "maybe", "comment": ""},
        {"comment": "x"},
        {"decision": "approve", "comment": "x" * 2001},
    ],
)
def test_bad_decision_is_422_and_writes_nothing(
    client: TestClient, engine: Engine, seeded: dict[str, uuid.UUID], body: dict[str, str]
) -> None:
    response = client.post(f"/breaks/{seeded['b1']}/decision", json=body)
    assert response.status_code == 422
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(AuditEvent)) == 0
