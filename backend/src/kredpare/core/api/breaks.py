"""Review API: list breaks, show one with both records and its explanation, record a decision.

A decision is only recorded in audit_events. Nothing is applied or sent (CLAUDE.md rule).
"""

import json
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, exists, func, select
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.db import get_sessionmaker
from kredpare.core.tables import AuditEvent, Break, ExplanationRow, Record

DECISION_ACTION = "break_decision"
DEFAULT_REVIEWER = "reviewer"
NO_LEVEL = "none"

ClauseResolver = Callable[[str, str], str | None]
"""(counterparty_id, citation) -> clause text, or None when it cannot be found.

The seam for clause text: the app is created with a resolver (see create_app). Without one,
citations are returned with text null."""


class Decision(StrEnum):
    approve = "approve"
    reject = "reject"


class RecordOut(BaseModel):
    id: uuid.UUID
    schema_name: str
    record_id: str
    row_number: int
    data: dict[str, str | None]
    """Canonical values as strings; money is the exact decimal string stored at ingest."""


class CitationOut(BaseModel):
    citation: str
    text: str | None


class ExplanationOut(BaseModel):
    level: str
    rule: str
    cause: str
    wrong_side: str | None
    proposal: str
    evidence: dict[str, Any]
    citations: list[CitationOut]


class DecisionOut(BaseModel):
    break_id: uuid.UUID
    decision: Decision
    comment: str
    actor: str
    occurred_at: datetime


class BreakSummary(BaseModel):
    id: uuid.UUID
    as_of: date
    break_type: str
    counterparty_id: str
    batch_id: str
    record_id: str
    field: str | None
    left_value: str | None
    right_value: str | None
    delta: str | None
    status: str
    level: str | None
    rule: str | None
    cause: str | None


class BreakPage(BaseModel):
    items: list[BreakSummary]
    total: int
    limit: int
    offset: int


class BreakDetail(BreakSummary):
    left_schema: str
    right_schema: str | None
    side_schema: str | None
    left_record: RecordOut | None
    right_record: RecordOut | None
    explanation: ExplanationOut | None
    decisions: list[DecisionOut]


class DecisionIn(BaseModel):
    decision: Decision
    comment: str = Field(default="", max_length=2000)


def get_session() -> Iterator[Session]:
    with get_sessionmaker()() as session:
        yield session


def get_clause_resolver(request: Request) -> ClauseResolver | None:
    return getattr(request.app.state, "clause_resolver", None)


SessionDep = Annotated[Session, Depends(get_session)]
ResolverDep = Annotated[ClauseResolver | None, Depends(get_clause_resolver)]

router = APIRouter(prefix="/breaks", tags=["breaks"])


def _decimal(value: Decimal | None) -> str | None:
    return None if value is None else format(value, "f")


def _latest_explanations(
    session: Session, break_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ExplanationRow]:
    """The newest explanation per break, so a deeper cascade level wins over an earlier one."""
    latest: dict[uuid.UUID, ExplanationRow] = {}
    rows = session.scalars(
        select(ExplanationRow)
        .where(ExplanationRow.break_id.in_(break_ids))
        .order_by(ExplanationRow.created_at, ExplanationRow.id)
    )
    for row in rows:
        latest[row.break_id] = row
    return latest


def _summary(row: Break, explanation: ExplanationRow | None) -> dict[str, Any]:
    return {
        "id": row.id,
        "as_of": row.as_of,
        "break_type": row.break_type,
        "counterparty_id": row.counterparty_id,
        "batch_id": row.batch_id,
        "record_id": row.record_id,
        "field": row.field,
        "left_value": row.left_value,
        "right_value": row.right_value,
        "delta": _decimal(row.delta),
        "status": row.status,
        "level": None if explanation is None else explanation.level,
        "rule": None if explanation is None else explanation.rule,
        "cause": None if explanation is None else explanation.cause,
    }


@router.get("", response_model=BreakPage)
def list_breaks(
    session: SessionDep,
    counterparty_id: str | None = None,
    break_type: str | None = None,
    status_: Annotated[str | None, Query(alias="status")] = None,
    level: Annotated[str | None, Query(description="Explanation level, or 'none'")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> BreakPage:
    conditions: list[ColumnElement[bool]] = []
    if counterparty_id is not None:
        conditions.append(Break.counterparty_id == counterparty_id)
    if break_type is not None:
        conditions.append(Break.break_type == break_type)
    if status_ is not None:
        conditions.append(Break.status == status_)
    if level is not None:
        has_level = exists().where(ExplanationRow.break_id == Break.id)
        if level == NO_LEVEL:
            conditions.append(~has_level)
        else:
            conditions.append(has_level.where(ExplanationRow.level == level))

    total = session.scalar(select(func.count()).select_from(Break).where(*conditions)) or 0
    rows = session.scalars(
        select(Break).where(*conditions).order_by(Break.key, Break.id).limit(limit).offset(offset)
    ).all()
    explanations = _latest_explanations(session, [r.id for r in rows])
    return BreakPage(
        items=[BreakSummary(**_summary(r, explanations.get(r.id))) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


def _record_out(session: Session, record_pk: uuid.UUID | None) -> RecordOut | None:
    row = None if record_pk is None else session.get(Record, record_pk)
    if row is None:
        return None
    return RecordOut(
        id=row.id,
        schema_name=row.schema_name,
        record_id=row.record_id,
        row_number=row.row_number,
        data={k: None if v is None else str(v) for k, v in row.data.items()},
    )


def _citation_name(raw: Any) -> str:
    return raw if isinstance(raw, str) else json.dumps(raw, sort_keys=True)


def _explanation_out(
    row: ExplanationRow, counterparty_id: str, resolver: ClauseResolver | None
) -> ExplanationOut:
    raw = row.evidence.get("citations")
    names = [_citation_name(c) for c in raw] if isinstance(raw, list) else []  # pyright: ignore[reportUnknownVariableType]
    return ExplanationOut(
        level=row.level,
        rule=row.rule,
        cause=row.cause,
        wrong_side=row.wrong_side,
        proposal=row.proposal,
        evidence=row.evidence,
        citations=[
            CitationOut(
                citation=name,
                text=None if resolver is None else resolver(counterparty_id, name),
            )
            for name in names
        ],
    )


def _decision_out(event: AuditEvent) -> DecisionOut:
    return DecisionOut(
        break_id=uuid.UUID(event.entity_id),
        decision=Decision(event.payload["decision"]),
        comment=str(event.payload.get("comment", "")),
        actor=event.actor,
        occurred_at=event.occurred_at,
    )


def _get_break(session: Session, break_id: uuid.UUID) -> Break:
    row = session.get(Break, break_id)
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "break not found")
    return row


@router.get("/{break_id}", response_model=BreakDetail)
def get_break(break_id: uuid.UUID, session: SessionDep, resolver: ResolverDep) -> BreakDetail:
    row = _get_break(session, break_id)
    explanation = _latest_explanations(session, [row.id]).get(row.id)
    events = session.scalars(
        select(AuditEvent)
        .where(
            AuditEvent.entity_type == "break",
            AuditEvent.entity_id == str(row.id),
            AuditEvent.action == DECISION_ACTION,
        )
        .order_by(AuditEvent.id)
    )
    return BreakDetail(
        **_summary(row, explanation),
        left_schema=row.left_schema,
        right_schema=row.right_schema,
        side_schema=row.side_schema,
        left_record=_record_out(session, row.left_record_id),
        right_record=_record_out(session, row.right_record_id),
        explanation=(
            None
            if explanation is None
            else _explanation_out(explanation, row.counterparty_id, resolver)
        ),
        decisions=[_decision_out(e) for e in events],
    )


@router.post("/{break_id}/decision", response_model=DecisionOut, status_code=201)
def decide(
    break_id: uuid.UUID,
    body: DecisionIn,
    session: SessionDep,
    reviewer: Annotated[str, Header(alias="X-Reviewer", min_length=1, max_length=100)] = (
        DEFAULT_REVIEWER
    ),
) -> DecisionOut:
    """Record the decision in audit_events. The break and its explanation stay untouched."""
    row = _get_break(session, break_id)
    event = record_event(
        session,
        reviewer,
        DECISION_ACTION,
        "break",
        str(row.id),
        {"decision": body.decision.value, "comment": body.comment},
    )
    session.commit()
    return _decision_out(event)
