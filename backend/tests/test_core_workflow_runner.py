import json
import re
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel
from sqlalchemy import Engine, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from kredpare.core.cases.llm import InvalidModelOutput, LLMResult, LLMUnavailable, ModelPrice
from kredpare.core.cases.runner import run_workflow_level
from kredpare.core.cases.workflow import ResponseCache, WorkflowExplanation
from kredpare.core.ingest import ingest_directory
from kredpare.core.matching.store import run_matching
from kredpare.core.rules.runner import run_rules
from kredpare.core.tables import AuditEvent, Break, ExplanationRow
from kredpare.domains.lending.pricing import DayCount, accrued_interest, purchase_price
from kredpare.domains.lending.spec import LENDING
from tests.test_core_ingest import _write

MODEL = "fake-model"
PRICES = {MODEL: ModelPrice(Decimal("1.00"), Decimal("2.00"), "test", "2026-10-07")}
AS_OF = date(2026, 9, 4)

_ACCRUED = accrued_interest(
    Decimal("20300.00"),
    Decimal("0.099900"),
    date(2026, 8, 20),
    date(2026, 9, 2),
    DayCount.ACTUAL_365,
)
_SELLER_TOTAL = purchase_price(Decimal("20300.00"), Decimal("1.010000"), _ACCRUED)
_CP_TOTAL = purchase_price(Decimal("20300.00"), Decimal("1.015000"), _ACCRUED)
SELLER = (
    "loan_id,batch_id,dealer_id,credit_tier,funding_date,cut_off_date,settlement_date,"
    "funded_amount,upb,note_rate,term_months,price_pct,accrued_interest,purchase_price\n"
    "L-004512,cp-quillmont-2026-09-02,D-0042,B,2026-08-20,2026-08-31,2026-09-02,"
    f"20300.00,20300.00,0.099900,60,1.010000,{_ACCRUED},{_SELLER_TOTAL}\n"
)
QUILLMONT = (
    "Loan Number,Settle Date,Principal Balance,Purchase Price %,Accrued Int,Total Price\n"
    f'L-004512,09/02/2026,"$20,300.00",101.500,${_ACCRUED},"${_CP_TOTAL:,}"\n'
)


class SmartFake:
    """Picks the first clause-supported candidate that reproduces the counterparty value."""

    def __init__(self, error: Exception | None = None) -> None:
        self.calls = 0
        self.error = error

    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        self.calls += 1
        if self.error is not None:
            raise self.error
        block = user.split("<candidates>")[1].split("</candidates>")[0]
        candidates = [json.loads(line) for line in block.strip().splitlines()]
        chosen = next(
            c for c in candidates if c["reproduces_counterparty_value"] and c["supported_by"]
        )
        reply = WorkflowExplanation(
            cause="price_grid_amendment",
            wrong_side="counterparty",
            candidate_id=chosen["id"],
            citations=["amendment-2 §4.1"],
            proposal="email",
            confidence=0.9,
            reasoning="Amendment 2 is in force for the 09-02 batch.",
        )
        assert isinstance(reply, schema)
        return LLMResult(reply, 1000, 100, 0.25, 1)


@pytest.fixture
def pending(engine: Engine, tmp_path: Path) -> Engine:
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (QUILLMONT, "PurchaseConfirmation", "cp-quillmont"),
        },
    )
    ingest_directory(engine, LENDING, tmp_path)
    run_matching(engine, LENDING, AS_OF)
    run_rules(engine, LENDING)
    return engine


_WORKFLOW_ROWS = select(ExplanationRow).where(ExplanationRow.level == "workflow")


def _statuses(engine: Engine) -> dict[str, str]:
    with Session(engine) as session:
        return {b.field or b.break_type: b.status for b in session.scalars(select(Break))}


def test_pending_breaks_are_explained_and_stored_with_audit(pending: Engine) -> None:
    assert set(_statuses(pending).values()) == {"pending_workflow"}
    llm = SmartFake()

    report = run_workflow_level(pending, LENDING, llm=llm, model=MODEL, prices=PRICES)

    assert (report.explained, report.needs_investigation, report.unavailable) == (2, 0, 0)
    assert report.llm_calls == 2 == llm.calls
    assert report.cost_usd == Decimal("0.0024")
    assert set(_statuses(pending).values()) == {"explained"}
    with Session(pending) as session:
        rows = session.scalars(_WORKFLOW_ROWS)
        stored = list(rows)
        assert len(stored) == 2
        row = next(r for r in stored if r.evidence["field"] == "price_pct")
        assert (row.cause, row.wrong_side, row.proposal) == (
            "price_grid_amendment",
            "counterparty",
            "email",
        )
        assert row.evidence["citations"] == ["amendment-2 §4.1"]
        assert row.evidence["candidate_id"] == "grid:base §4.1"
        assert row.evidence["candidate"]["value"] == "1.0150"
        assert row.evidence["confidence"] == 0.9
        assert row.evidence["model"] == MODEL
        events = session.scalars(select(AuditEvent).order_by(AuditEvent.id)).all()
        calls = [e for e in events if e.action == "workflow_llm_call"]
        changes = [
            e
            for e in events
            if e.action == "break_status_changed" and e.payload["new_status"] == "explained"
        ]
        assert len(calls) == len(changes) == 2
        payload = calls[0].payload
        assert (payload["model"], payload["prompt_version"]) == (MODEL, "lending-workflow-v1")
        assert (payload["input_tokens"], payload["output_tokens"]) == (1000, 100)
        assert payload["llm_called"] is True and payload["cached"] is False
        assert payload["retries"] == 1 and payload["cost_usd"] == "0.0012"
        assert changes[0].payload["old_status"] == "pending_workflow"
        assert changes[0].actor == "workflow"


def test_rerun_finds_nothing_left_to_do(pending: Engine) -> None:
    llm = SmartFake()
    run_workflow_level(pending, LENDING, llm=llm, model=MODEL, prices=PRICES)

    again = run_workflow_level(pending, LENDING, llm=llm, model=MODEL, prices=PRICES)

    assert (again.explained, again.needs_investigation, again.llm_calls) == (0, 0, 0)
    assert llm.calls == 2
    with Session(pending) as session:
        assert len(session.scalars(select(ExplanationRow)).all()) == 2


def test_cache_makes_a_second_database_free(pending: Engine, tmp_path: Path) -> None:
    cache = ResponseCache(tmp_path / "cache")
    first = SmartFake()
    run_workflow_level(pending, LENDING, llm=first, model=MODEL, cache=cache, prices=PRICES)
    with Session(pending) as session:
        session.execute(text("UPDATE breaks SET status = 'pending_workflow'"))
        session.execute(text("DELETE FROM explanations WHERE level = 'workflow'"))
        session.commit()
    second = SmartFake()

    report = run_workflow_level(
        pending, LENDING, llm=second, model=MODEL, cache=cache, prices=PRICES
    )

    assert second.calls == 0
    assert report.explained == 2 and report.cached == 2
    with Session(pending) as session:
        last = session.scalars(
            select(AuditEvent)
            .where(AuditEvent.action == "workflow_llm_call")
            .order_by(AuditEvent.id.desc())
        ).first()
        assert last is not None and last.payload["cached"] is True


def test_invalid_output_marks_needs_investigation_with_the_reason(pending: Engine) -> None:
    error = InvalidModelOutput("empty reply", input_tokens=900, output_tokens=0, latency_seconds=1)

    report = run_workflow_level(pending, LENDING, llm=SmartFake(error), model=MODEL, prices=PRICES)

    assert report.needs_investigation == 2 and report.invalid_outputs == 2
    assert set(_statuses(pending).values()) == {"needs_investigation"}
    with Session(pending) as session:
        assert session.scalars(_WORKFLOW_ROWS).all() == []
        event = session.scalars(
            select(AuditEvent).where(
                AuditEvent.payload["new_status"].astext == "needs_investigation"
            )
        ).first()
        assert event is not None
        assert event.payload["reasons"] == ["invalid_model_output: empty reply"]


def test_unavailable_provider_leaves_breaks_pending_for_a_rerun(pending: Engine) -> None:
    report = run_workflow_level(
        pending,
        LENDING,
        llm=SmartFake(LLMUnavailable("down", retries=5)),
        model=MODEL,
        prices=PRICES,
    )

    assert (report.unavailable, report.explained, report.needs_investigation) == (2, 0, 0)
    assert set(_statuses(pending).values()) == {"pending_workflow"}
    again = run_workflow_level(pending, LENDING, llm=SmartFake(), model=MODEL, prices=PRICES)
    assert again.explained == 2


def test_break_without_candidates_is_short_circuited_without_a_call(
    engine: Engine, tmp_path: Path
) -> None:
    moved = QUILLMONT.replace("09/02/2026", "09/03/2026")
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (moved, "PurchaseConfirmation", "cp-quillmont"),
        },
    )
    ingest_directory(engine, LENDING, tmp_path)
    run_matching(engine, LENDING, AS_OF)
    run_rules(engine, LENDING)
    llm = SmartFake()

    report = run_workflow_level(engine, LENDING, llm=llm, model=MODEL, prices=PRICES)

    assert report.short_circuited == 1
    assert report.llm_calls == llm.calls == 2
    assert report.needs_investigation == 1 and report.explained == 2
    with Session(engine) as session:
        event = session.scalars(
            select(AuditEvent).where(
                AuditEvent.payload["reasons"].astext.contains("no_supported_candidate")
            )
        ).one()
        assert event.payload["llm_called"] is False
        assert event.payload["new_status"] == "needs_investigation"


def test_domain_without_a_workflow_is_rejected(pending: Engine) -> None:
    with pytest.raises(ValueError, match="no workflow"):
        run_workflow_level(
            pending, replace(LENDING, workflow=None), llm=SmartFake(), model=MODEL, prices=PRICES
        )


def test_database_accepts_workflow_level_only_with_a_valid_side(pending: Engine) -> None:
    run_workflow_level(pending, LENDING, llm=SmartFake(), model=MODEL, prices=PRICES)
    with Session(pending) as session:
        row = session.scalars(_WORKFLOW_ROWS).first()
        assert row is not None
        session.add(
            ExplanationRow(
                break_id=row.break_id,
                level="agent",
                rule="x",
                cause="c",
                wrong_side=None,
                proposal="email",
                evidence={},
            )
        )
        with pytest.raises(IntegrityError):
            session.commit()


def test_lending_domain_declares_its_workflow() -> None:
    assert LENDING.workflow is not None
    assert re.fullmatch(r"lending-workflow-v\d+", LENDING.workflow.prompt_version)
