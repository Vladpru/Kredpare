import hashlib
import json
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from kredpare.core.ingest import ingest_directory
from kredpare.core.tables import AuditEvent, File, MappingConfigRow, Record, RowErrorRow
from kredpare.domains.lending.spec import LENDING

SELLER = (
    "loan_id,batch_id,dealer_id,credit_tier,funding_date,cut_off_date,settlement_date,"
    "funded_amount,upb,note_rate,term_months,price_pct,accrued_interest,purchase_price\n"
    "L-004512,cp-quillmont-2026-09-02,D-0042,B,2026-08-20,2026-08-31,2026-09-02,"
    "20300.00,20300.00,0.099900,60,1.015000,72.23,20676.73\n"
    "L-004513,cp-quillmont-2026-09-02,D-0042,B,2026-08-20,2026-08-31,2026-09-02,"
    "20300.00,20300.00,0.099900,60,1.015000,72.23,20676.74\n"
)
QUILLMONT = (
    "Loan Number,Settle Date,Principal Balance,Purchase Price %,Accrued Int,Total Price\n"
    'L-004512,09/02/2026,"$20,300.00",101.500,$72.23,"$20,676.73"\n'
    'L-004513,2026-09-02,"$20,300.00",101.500,$72.23,"$20,676.74"\n'
)
UNKNOWN = "foo,bar\n1,2\n"


def _write(directory: Path, files: dict[str, tuple[str, str, str]]) -> None:
    """files: path -> (content, schema_name, counterparty_id)."""
    lines = []
    for path, (content, schema, counterparty) in files.items():
        (directory / path).parent.mkdir(parents=True, exist_ok=True)
        (directory / path).write_text(content)
        lines.append(
            json.dumps(
                {
                    "path": path,
                    "counterparty_id": counterparty,
                    "schema_name": schema,
                    "batch_id": "cp-quillmont-2026-09-02",
                    "sha256": hashlib.sha256(content.encode()).hexdigest(),
                }
            )
        )
    (directory / "manifest.jsonl").write_text("\n".join(lines) + "\n")


@pytest.fixture
def dataset(tmp_path: Path) -> Path:
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (QUILLMONT, "PurchaseConfirmation", "cp-quillmont"),
            "cp-mystery/a.csv": (UNKNOWN, "PurchaseConfirmation", "cp-mystery"),
        },
    )
    return tmp_path


def _count(session: Session, table: type) -> int:
    return session.scalar(select(func.count()).select_from(table)) or 0


def test_ingest_stores_valid_rows_and_keeps_invalid_rows_as_errors(
    engine: Engine, dataset: Path
) -> None:
    outcomes = ingest_directory(engine, LENDING, dataset)

    assert [(o.path, o.status, o.rows, o.errors) for o in outcomes] == [
        ("seller/a.csv", "ingested", 1, 1),
        ("cp-quillmont/a.csv", "ingested", 1, 1),
        ("cp-mystery/a.csv", "unmapped", 0, 0),
    ]
    with Session(engine) as session:
        confirmation = session.scalars(
            select(Record).where(Record.schema_name == "PurchaseConfirmation")
        ).one()
        assert (confirmation.record_id, confirmation.batch_id) == (
            "L-004512",
            "cp-quillmont-2026-09-02",
        )
        assert confirmation.data["upb"] == "20300.00"
        assert confirmation.data["price_pct"] == "1.015000"
        assert confirmation.data["settlement_date"] == "2026-09-02"
        errors = session.scalars(select(RowErrorRow).order_by(RowErrorRow.id)).all()
        assert [e.row_number for e in errors] == [2, 2]
        assert "purchase_price" in errors[0].messages[0]
        assert "Settle Date" in errors[1].messages[0]


def test_ingest_seeds_mapping_configs_once(engine: Engine, dataset: Path) -> None:
    ingest_directory(engine, LENDING, dataset)
    ingest_directory(engine, LENDING, dataset)

    with Session(engine) as session:
        rows = session.scalars(select(MappingConfigRow)).all()
        assert sorted(r.name for r in rows) == sorted(m.name for m in LENDING.mappings)
        assert {(r.version, r.status) for r in rows} == {(1, "active")}


def test_reingest_is_idempotent(engine: Engine, dataset: Path) -> None:
    ingest_directory(engine, LENDING, dataset)
    with Session(engine) as session:
        before = [_count(session, t) for t in (File, Record, RowErrorRow, AuditEvent)]

    outcomes = ingest_directory(engine, LENDING, dataset)

    assert {o.status for o in outcomes} == {"skipped"}
    with Session(engine) as session:
        assert [_count(session, t) for t in (File, Record, RowErrorRow, AuditEvent)] == before


def test_checksum_mismatch_rejects_the_file(engine: Engine, dataset: Path) -> None:
    (dataset / "seller/a.csv").write_text(SELLER + "tampered\n")

    outcome = ingest_directory(engine, LENDING, dataset)[0]

    assert (outcome.status, outcome.rows) == ("rejected", 0)
    assert "sha256" in (outcome.message or "")


def test_every_file_outcome_is_audited(engine: Engine, dataset: Path) -> None:
    ingest_directory(engine, LENDING, dataset)

    with Session(engine) as session:
        actions = session.scalars(select(AuditEvent.action)).all()
    assert actions.count("mapping_config_created") == len(LENDING.mappings)
    assert actions.count("file_ingested") == 2
    assert actions.count("file_unmapped") == 1
