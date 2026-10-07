from datetime import date
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.cli import _explain
from kredpare.core.ingest import ingest_directory
from kredpare.core.matching.store import run_matching
from kredpare.core.tables import Break
from kredpare.domains.lending.spec import LENDING
from tests.test_core_ingest import SELLER, _write
from tests.test_core_rules import OFF_BY_A_CENT


def test_explain_runs_the_lending_rules_and_prints_counts(
    engine: Engine, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (OFF_BY_A_CENT, "PurchaseConfirmation", "cp-quillmont"),
        },
    )
    ingest_directory(engine, LENDING, tmp_path)
    run_matching(engine, LENDING, date(2026, 9, 4))

    assert _explain(engine) == 0

    # 72.23 vs 72.22: truncating the seller's own computation reproduces the counterparty value.
    assert "1 explained, 0 pending_workflow" in capsys.readouterr().out
    with Session(engine) as session:
        assert session.scalars(select(Break.status)).one() == "explained"
