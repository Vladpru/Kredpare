import json
from decimal import Decimal

import pytest

from kredpare.domains.lending.evals import (
    Label,
    WorkflowVerdict,
    expected_labels,
    score_workflow,
)

M1 = ("amount_mismatch", "L-1", "accrued_interest")
M2 = ("amount_mismatch", "L-1", "purchase_price")
M3 = ("amount_mismatch", "L-2", "price_pct")
M4 = ("amount_mismatch", "L-3", "price_pct")
H1 = ("amount_mismatch", "L-9", "accrued_interest")
H2 = ("amount_mismatch", "L-8", "accrued_interest")


def _label(difficulty: str, cause: str, citations: tuple[str, ...] = ()) -> Label:
    return Label(cause, difficulty, "counterparty", "email", citations)


LABELS = {
    M1: _label("medium", "accrued_interest_error", ("amendment-1 §4.2",)),
    M2: _label("medium", "accrued_interest_error", ("amendment-1 §4.2",)),
    M3: _label("medium", "price_grid_amendment", ("amendment-2 §4.1",)),
    M4: _label("medium", "price_grid_amendment", ("amendment-2 §4.1",)),
    H1: _label("hard", "unannounced_rule_change"),
    H2: _label("hard", "combined_causes"),
}


def _v(
    status: str = "explained",
    cause: str | None = "accrued_interest_error",
    side: str | None = "counterparty",
    citations: tuple[str, ...] = ("amendment-1 §4.2",),
    llm_called: bool = True,
    cost: str = "0.001",
    latency: float = 1.0,
    invalid: bool = False,
) -> WorkflowVerdict:
    return WorkflowVerdict(
        status, cause, side, "email", citations, llm_called, Decimal(cost), latency, invalid
    )


def test_labels_carry_expected_citations() -> None:
    line = json.dumps(
        {
            "break_type": "amount_mismatch",
            "batch_ids": ["cp-b-2026-08-31"],
            "loan_ids": ["L-1"],
            "fields": ["accrued_interest"],
            "wrong_side": "counterparty",
            "difficulty": "medium",
            "cause": "accrued_interest_error",
            "expected_proposal": "email",
            "expected_citations": ["amendment-1 §4.2"],
        }
    )

    label = expected_labels([line])[M1]

    assert label.citations == ("amendment-1 §4.2",)


def test_scores_s4_s5_side_and_s6() -> None:
    verdicts = {
        M1: _v(),
        M2: _v(citations=("amendment-1 §4.2", "base §4.2")),
        M3: _v(cause="accrued_interest_error", citations=("amendment-2 §4.1",)),
        M4: _v(status="needs_investigation", cause=None, side=None, citations=()),
        H1: _v(status="needs_investigation", cause=None, llm_called=False, cost="0"),
        H2: _v(),
    }

    score = score_workflow(LABELS, verdicts)

    assert score.medium_support == 4
    assert score.s4 == pytest.approx(2 / 4)
    assert score.s5 == pytest.approx(2 / 4)
    assert score.s5_superset == pytest.approx(3 / 4)
    assert score.wrong_side_accuracy == pytest.approx(3 / 4)
    assert score.hard_support == 2
    assert score.s6 == pytest.approx(1 / 2)


def test_cost_calls_latency_and_invalid_outputs() -> None:
    verdicts = {
        M1: _v(cost="0.002", latency=1.0),
        M2: _v(cost="0.004", latency=3.0, invalid=True, status="needs_investigation"),
        H1: _v(status="needs_investigation", llm_called=False, cost="0", latency=0.0),
    }

    score = score_workflow(LABELS, verdicts)

    assert score.reached_workflow == 3
    assert score.llm_calls == 2 and score.short_circuited == 1
    assert score.total_cost == Decimal("0.006")
    assert score.cost_per_break == Decimal("0.002")
    assert score.cost_per_call == Decimal("0.003")
    assert score.invalid_outputs == 1
    assert (score.latency_p50, score.latency_p95) == (2.0, pytest.approx(2.9))


def test_breaks_that_never_reached_the_workflow_count_against_medium_and_hard() -> None:
    score = score_workflow(LABELS, {})

    assert (score.s4, score.s5, score.s6) == (0.0, 0.0, 0.0)
    assert score.reached_workflow == 0
    assert score.cost_per_break == Decimal(0)
    assert score.latency_p50 == 0.0


def test_unlabeled_breaks_are_listed() -> None:
    score = score_workflow(LABELS, {("amount_mismatch", "L-77", "price_pct"): _v()})

    assert score.unlabeled == (("amount_mismatch", "L-77", "price_pct"),)
