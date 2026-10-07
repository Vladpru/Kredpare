"""End to end: datagen output → ingest, matching, rules, workflow (fake model) → eval.

No network: a fake model that reads the candidates in the prompt stands in for the LLM. Needs the
database from `make up`; the eval creates and drops its own database.
"""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from kredpare.cli import _eval_workflow, _WorkflowRuntime
from kredpare.core.cases.llm import LLMResult
from kredpare.core.cases.workflow import ResponseCache, WorkflowExplanation
from pydantic import BaseModel

from kredpare_datagen.cli import main as datagen

AS_OF = date(2026, 9, 8)


class OracleFake:
    """Explains from the candidates: cites the clause behind the candidate that reproduces the
    seller value, blames the counterparty. Confident even when no clause supports anything."""

    def __init__(self) -> None:
        self.calls = 0

    def complete[S: BaseModel](
        self, *, model: str, system: str, user: str, schema: type[S]
    ) -> LLMResult[S]:
        self.calls += 1
        block = user.split("<candidates>")[1].split("</candidates>")[0]
        candidates = [json.loads(line) for line in block.strip().splitlines()]
        wrong = next(
            c for c in candidates if c["reproduces_counterparty_value"] and c["supported_by"]
        )
        right = next(
            (c for c in candidates if c["reproduces_seller_value"] and c["supported_by"]), wrong
        )
        reply = WorkflowExplanation(
            cause="price_grid_amendment"
            if wrong["field"] != "accrued_interest"
            else "accrued_interest_error",
            wrong_side="counterparty",
            candidate_id=wrong["id"],
            citations=[right["supported_by"][-1]],
            proposal="email",
            confidence=0.95,
            reasoning="fake",
        )
        assert isinstance(reply, schema)
        return LLMResult(reply, 2000, 100, 0.5)


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dataset")
    assert datagen(["--seed", "42", "--out", str(out)]) == 0
    return out


def test_eval_workflow_scores_with_a_fake_model(
    dataset: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    llm = OracleFake()
    runtime = _WorkflowRuntime(llm, "gemini-3.5-flash-lite", 0.7, ResponseCache(tmp_path / "c"))

    code = _eval_workflow(dataset, AS_OF, None, False, Decimal("1"), runtime=runtime)

    out = capsys.readouterr().out
    assert code == 0
    assert llm.calls > 0
    for needle in ("S4 ", "S5 ", "S6 ", "S7 ", "p50", "invalid outputs", "S2 "):
        assert needle in out
    assert "short-circuited" in out

    # A second run reads every reply from the cache: no new calls.
    before = llm.calls
    assert _eval_workflow(dataset, AS_OF, None, False, Decimal("1"), runtime=runtime) == 0
    assert llm.calls == before
