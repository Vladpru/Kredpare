import json

from kredpare.core.matching import DetectedBreak
from kredpare.domains.lending.evals import actual_keys, expected_keys, score


def _gt(**fields: object) -> str:
    record: dict[str, object] = {
        "batch_ids": ["cp-q-2026-09-02"],
        "loan_ids": ["L-1"],
        "fields": [],
        "missing_side": None,
        "wrong_side": "counterparty",
    }
    record.update(fields)
    return json.dumps(record)


def _found(break_type: str, **fields: object) -> DetectedBreak:
    values: dict[str, object] = {
        "left_schema": "FundedLoan",
        "right_schema": "PurchaseConfirmation",
        "side_schema": None,
        "counterparty_id": "cp-q",
        "batch_id": "cp-q-2026-09-02",
        "record_id": "L-1",
    }
    values.update(fields)
    return DetectedBreak(break_type, **values)  # type: ignore[arg-type]


def test_expected_keys_expand_loans_times_fields() -> None:
    lines = [
        _gt(
            break_type="amount_mismatch",
            loan_ids=["L-1", "L-2"],
            fields=["accrued_interest", "purchase_price"],
        ),
        _gt(break_type="missing_record", missing_side="counterparty"),
        _gt(break_type="duplicate", wrong_side="seller"),
        _gt(break_type="stale_pending", wrong_side=None),
    ]

    assert expected_keys(lines) == {
        ("amount_mismatch", "L-1", "accrued_interest"),
        ("amount_mismatch", "L-1", "purchase_price"),
        ("amount_mismatch", "L-2", "accrued_interest"),
        ("amount_mismatch", "L-2", "purchase_price"),
        ("missing_record", "cp-q-2026-09-02", "L-1", "counterparty"),
        ("duplicate", "cp-q-2026-09-02", "L-1", "seller"),
        ("stale_pending", "cp-q-2026-09-02", "L-1", "counterparty"),
    }


def test_actual_keys_name_sides_like_ground_truth() -> None:
    found = [
        _found("amount_mismatch", field="upb"),
        _found("missing_record", side_schema="PurchaseConfirmation"),
        _found("duplicate", side_schema="FundedLoan"),
        _found("stale_pending", side_schema="ServicerOnboarding"),
    ]

    assert actual_keys(found) == {
        ("amount_mismatch", "L-1", "upb"),
        ("missing_record", "cp-q-2026-09-02", "L-1", "counterparty"),
        ("duplicate", "cp-q-2026-09-02", "L-1", "seller"),
        ("stale_pending", "cp-q-2026-09-02", "L-1", "servicer"),
    }


def test_score_per_break_type() -> None:
    expected = {("amount_mismatch", "L-1", "upb"), ("amount_mismatch", "L-2", "upb")}
    actual = {("amount_mismatch", "L-1", "upb"), ("amount_mismatch", "L-3", "upb")}

    result = score(expected, actual)

    assert result["amount_mismatch"].precision == 0.5
    assert result["amount_mismatch"].recall == 0.5
    assert result["amount_mismatch"].support == 2
    assert result["missing_record"].precision == 1.0  # nothing expected, nothing found
    assert result["missing_record"].recall == 1.0
