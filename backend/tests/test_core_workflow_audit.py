from decimal import Decimal

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.core.cases.llm import MODEL_PRICES, UnknownModelPrice, cost_usd
from kredpare.core.cases.workflow import (
    WorkflowExplanation,
    WorkflowResult,
    WorkflowStatus,
    WorkflowUsage,
    audit_payload,
    record_workflow_call,
)
from kredpare.core.tables import AuditEvent


def _result() -> WorkflowResult:
    usage = WorkflowUsage(
        model="gemini-3.5-flash-lite",
        prompt_version="p-v1",
        input_tokens=3000,
        output_tokens=200,
        cost_usd=cost_usd("gemini-3.5-flash-lite", 3000, 200),
        latency_seconds=1.25,
        cached=False,
        retries=2,
    )
    explanation = WorkflowExplanation(
        cause="accrued_interest_error",
        wrong_side="counterparty",
        candidate_id="c",
        citations=["amendment-1 §4.2"],
        proposal="email",
        confidence=0.9,
        reasoning="r",
    )
    return WorkflowResult(WorkflowStatus.EXPLAINED, [], explanation, [], usage, "abc")


def test_cost_is_exact_decimal_per_million_tokens() -> None:
    assert cost_usd("gemini-3.5-flash-lite", 1_000_000, 1_000_000) == Decimal("2.80")
    assert cost_usd("gemini-3.5-flash", 3000, 200) == Decimal("0.0063")


def test_price_rows_record_source_and_date() -> None:
    for price in MODEL_PRICES.values():
        assert price.source.startswith("https://ai.google.dev/gemini-api/docs/pricing")
        assert price.checked_on == "2026-10-07"


def test_unpriced_model_raises_instead_of_costing_zero() -> None:
    with pytest.raises(UnknownModelPrice):
        cost_usd("mystery-model", 1, 1)


def test_audit_payload_has_model_prompt_version_tokens_and_cost() -> None:
    payload = audit_payload(_result())

    assert payload["model"] == "gemini-3.5-flash-lite"
    assert payload["prompt_version"] == "p-v1"
    assert (payload["input_tokens"], payload["output_tokens"]) == (3000, 200)
    assert payload["cost_usd"] == "0.0014"
    assert payload["status"] == "explained"
    assert payload["retries"] == 2
    assert payload["llm_called"] is True
    assert "reasoning" not in payload


def test_record_workflow_call_writes_an_audit_event(engine: Engine) -> None:
    with Session(engine) as session:
        record_workflow_call(session, _result(), break_id="brk-1")
        session.commit()

    with Session(engine) as session:
        event = session.scalars(select(AuditEvent)).one()
        assert (event.action, event.entity_type, event.entity_id) == (
            "workflow_llm_call",
            "break",
            "brk-1",
        )
        assert event.payload["model"] == "gemini-3.5-flash-lite"
        assert event.payload["prompt_hash"] == "abc"
