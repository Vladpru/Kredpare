"""Workflow level of the cascade: explain the breaks the rules left in `pending_workflow`.

Each break is handled in its own transaction: its status change, its explanation, and its audit
events commit together, so a crash loses at most the break in flight (and the reply cache keeps
what the model already said). Rerunning only touches `pending_workflow` breaks.
"""

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.cases.llm import LLMClient, LLMUnavailable, ModelPrice
from kredpare.core.cases.workflow import (
    DEFAULT_CONFIDENCE_THRESHOLD,
    ResponseCache,
    WorkflowBreak,
    WorkflowResult,
    WorkflowStatus,
    audit_payload,
    record_workflow_call,
    run_workflow,
)
from kredpare.core.domain import DomainSpec
from kredpare.core.rules.runner import EXPLAINED, PENDING_WORKFLOW
from kredpare.core.tables import Break, ExplanationRow, Record

NEEDS_INVESTIGATION = "needs_investigation"
INVALID_OUTPUT_PREFIX = "invalid_model_output"
_SIDES = {"seller": "seller", "counterparty": "counterparty"}


@dataclass(frozen=True)
class WorkflowOutcome:
    break_id: uuid.UUID
    result: WorkflowResult


@dataclass(frozen=True)
class WorkflowReport:
    explained: int = 0
    needs_investigation: int = 0
    unavailable: int = 0
    """Breaks left in pending_workflow because the provider kept failing."""
    llm_calls: int = 0
    """Breaks whose reply came from the model or the cache (not short-circuited)."""
    cached: int = 0
    short_circuited: int = 0
    """Breaks closed by code alone: no clause-supported candidate, no call."""
    invalid_outputs: int = 0
    retries: int = 0
    cost_usd: Decimal = Decimal(0)
    """Cost of the calls of this run, including calls served from the cache at their original
    price."""
    spent_usd: Decimal = Decimal(0)
    """Money actually spent by this run: calls served from the cache cost nothing now."""
    stopped_by_budget: bool = False
    outcomes: list[WorkflowOutcome] = field(default_factory=list[WorkflowOutcome])


def _record_data(session: Session, record_pk: uuid.UUID | None) -> dict[str, object]:
    row = None if record_pk is None else session.get(Record, record_pk)
    return {} if row is None else dict(row.data)


def _workflow_break(session: Session, row: Break) -> WorkflowBreak:
    return WorkflowBreak(
        counterparty_id=row.counterparty_id,
        field=row.field or "",
        seller_value=row.left_value,
        counterparty_value=row.right_value,
        seller_record=_record_data(session, row.left_record_id),
        counterparty_record=_record_data(session, row.right_record_id),
    )


def run_workflow_level(
    engine: Engine,
    domain: DomainSpec,
    *,
    llm: LLMClient,
    model: str,
    threshold: float = DEFAULT_CONFIDENCE_THRESHOLD,
    cache: ResponseCache | None = None,
    prices: dict[str, ModelPrice] | None = None,
    actor: str = "workflow",
    max_spend_usd: Decimal | None = None,
) -> WorkflowReport:
    """Explain every pending_workflow break; stop early once `max_spend_usd` is exceeded.

    Breaks not reached stay pending_workflow, so a rerun continues where this one stopped.
    """
    if domain.workflow is None:
        raise ValueError(f"domain {domain.name!r} has no workflow")
    spec = domain.workflow
    totals = _Totals()
    with Session(engine) as session:
        ids = session.scalars(
            select(Break.id).where(Break.status == PENDING_WORKFLOW).order_by(Break.key)
        ).all()
    for break_id in ids:
        if max_spend_usd is not None and totals.spent > max_spend_usd:
            totals.stopped = True
            break
        with Session(engine) as session:
            row = session.get(Break, break_id)
            if row is None or row.status != PENDING_WORKFLOW:
                continue
            try:
                result = run_workflow(
                    spec,
                    _workflow_break(session, row),
                    llm=llm,
                    model=model,
                    threshold=threshold,
                    cache=cache,
                    prices=prices,
                )
            except LLMUnavailable:
                totals.unavailable += 1
                continue
            _store(session, row, result, actor)
            session.commit()
            totals.add(break_id, result)
    return totals.report()


def _store(session: Session, row: Break, result: WorkflowResult, actor: str) -> None:
    payload: dict[str, object] = {"old_status": PENDING_WORKFLOW, **audit_payload(result)}
    explanation = result.explanation
    if result.status is WorkflowStatus.EXPLAINED and explanation is not None:
        cited = next(c for c in result.candidates if c["id"] == explanation.candidate_id)
        stored = ExplanationRow(
            id=uuid.uuid4(),
            break_id=row.id,
            level="workflow",
            rule="workflow",
            cause=explanation.cause,
            wrong_side=_SIDES[explanation.wrong_side],
            proposal=explanation.proposal,
            evidence={
                "field": row.field,
                "candidate_id": explanation.candidate_id,
                "candidate": dict(cited),
                "citations": explanation.citations,
                "confidence": explanation.confidence,
                "reasoning": explanation.reasoning,
                "model": result.usage.model,
                "prompt_version": result.usage.prompt_version,
                "prompt_hash": result.prompt_hash,
            },
        )
        session.add(stored)
        session.flush()
        row.status = EXPLAINED
        payload |= {
            "new_status": EXPLAINED,
            "explanation_id": str(stored.id),
            "cause": explanation.cause,
        }
    else:
        row.status = NEEDS_INVESTIGATION
        payload["new_status"] = NEEDS_INVESTIGATION
    if result.usage.llm_called:
        record_workflow_call(session, result, break_id=str(row.id), actor=actor)
    record_event(session, actor, "break_status_changed", "break", str(row.id), payload)


class _Totals:
    def __init__(self) -> None:
        self.explained = self.needs = self.unavailable = 0
        self.calls = self.cached = self.short = self.invalid = self.retries = 0
        self.cost = self.spent = Decimal(0)
        self.stopped = False
        self.outcomes: list[WorkflowOutcome] = []

    def add(self, break_id: uuid.UUID, result: WorkflowResult) -> None:
        if result.status is WorkflowStatus.EXPLAINED:
            self.explained += 1
        else:
            self.needs += 1
        usage = result.usage
        if usage.llm_called:
            self.calls += 1
            self.cached += usage.cached
            self.retries += usage.retries
            self.cost += usage.cost_usd
            if not usage.cached:
                self.spent += usage.cost_usd
        else:
            self.short += 1
        if any(r.startswith(INVALID_OUTPUT_PREFIX) for r in result.reasons):
            self.invalid += 1
        self.outcomes.append(WorkflowOutcome(break_id, result))

    def report(self) -> WorkflowReport:
        return WorkflowReport(
            self.explained,
            self.needs,
            self.unavailable,
            self.calls,
            self.cached,
            self.short,
            self.invalid,
            self.retries,
            self.cost,
            self.spent,
            self.stopped,
            self.outcomes,
        )
