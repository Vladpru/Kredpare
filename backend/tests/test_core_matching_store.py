from datetime import date
from pathlib import Path

from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kredpare.core.ingest import ingest_directory
from kredpare.core.matching.store import run_matching
from kredpare.core.tables import AuditEvent, Break, Record
from kredpare.domains.lending.spec import LENDING
from tests.test_core_ingest import SELLER, _write

QUILLMONT_OFF_BY_A_CENT = (
    "Loan Number,Settle Date,Principal Balance,Purchase Price %,Accrued Int,Total Price\n"
    'L-004512,09/02/2026,"$20,300.00",101.500,$72.22,"$20,676.73"\n'
)
AS_OF = date(2026, 9, 4)


def _ingest(engine: Engine, tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (QUILLMONT_OFF_BY_A_CENT, "PurchaseConfirmation", "cp-quillmont"),
        },
    )
    ingest_directory(engine, LENDING, tmp_path)


def test_run_matching_stores_breaks_and_statuses(engine: Engine, tmp_path: Path) -> None:
    _ingest(engine, tmp_path)

    report = run_matching(engine, LENDING, AS_OF)

    assert report.created == {"amount_mismatch": 1}
    with Session(engine) as session:
        found = session.scalars(select(Break)).one()
        assert (found.break_type, found.record_id, found.field) == (
            "amount_mismatch",
            "L-004512",
            "accrued_interest",
        )
        assert (found.left_value, found.right_value, str(found.delta)) == (
            "72.23",
            "72.22",
            "-0.010000",
        )
        assert set(session.scalars(select(Record.match_status))) == {"in_break"}
        actions = session.scalars(select(AuditEvent.action)).all()
        assert actions.count("break_detected") == 1
        assert actions.count("matching_run") == 1


def test_rerun_for_the_same_as_of_does_not_duplicate_breaks(engine: Engine, tmp_path: Path) -> None:
    _ingest(engine, tmp_path)
    run_matching(engine, LENDING, AS_OF)

    report = run_matching(engine, LENDING, AS_OF)

    assert report.created == {}
    assert report.detected == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Break)) == 1
        actions = session.scalars(select(AuditEvent.action)).all()
        assert actions.count("break_detected") == 1
