import pytest

from kredpare.domains.lending.tools.query_records import QueryRecords
from tests.fake_context import (
    BATCH,
    CONFIRMATION,
    CP,
    LOAN,
    SELLER,
    FakeContext,
    make_record,
)

OTHER_BATCH = "cp-quillmont-2026-09-09"


def _context() -> FakeContext:
    return FakeContext(
        [
            make_record(SELLER, data={"loan_id": LOAN, "upb": "100.00"}),
            make_record(CONFIRMATION, data={"loan_id": LOAN, "upb": "100.00"}),
            make_record(SELLER, loan="L-000002", batch=OTHER_BATCH, data={"loan_id": "L-000002"}),
            make_record(SELLER, counterparty="cp-other", data={"loan_id": LOAN}),
        ]
    )


def test_query_records_is_named_for_the_tool_registry() -> None:
    assert QueryRecords().name == "query_records"


def test_filters_by_loan_batch_counterparty_and_schema() -> None:
    query = QueryRecords()

    rows = query(_context(), counterparty_id=CP, batch_id=BATCH, loan_id=LOAN, schema=SELLER)

    assert rows == [
        {
            "schema": SELLER,
            "counterparty_id": CP,
            "batch_id": BATCH,
            "loan_id": LOAN,
            "row_number": 1,
            "data": {"loan_id": LOAN, "upb": "100.00"},
        }
    ]


def test_loan_filter_alone_returns_every_schema_and_counterparty() -> None:
    rows = QueryRecords()(_context(), loan_id=LOAN)

    assert {(r["schema"], r["counterparty_id"]) for r in rows} == {
        (SELLER, CP),
        (CONFIRMATION, CP),
        (SELLER, "cp-other"),
    }


def test_limit_caps_the_rows() -> None:
    assert len(QueryRecords()(_context(), loan_id=LOAN, limit=2)) == 2


def test_a_query_without_a_filter_is_rejected() -> None:
    with pytest.raises(ValueError, match="filter"):
        QueryRecords()(_context())


def test_an_unknown_schema_is_rejected() -> None:
    with pytest.raises(ValueError, match="schema"):
        QueryRecords()(_context(), schema="Nope")


@pytest.mark.parametrize("limit", [0, -1, 501])
def test_a_limit_out_of_range_is_rejected(limit: int) -> None:
    with pytest.raises(ValueError, match="limit"):
        QueryRecords()(_context(), loan_id=LOAN, limit=limit)


def test_filter_values_are_data_not_sql() -> None:
    assert QueryRecords()(_context(), loan_id="L-1'; DROP TABLE records; --") == []
