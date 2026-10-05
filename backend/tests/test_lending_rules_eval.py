import json

from kredpare.domains.lending.evals import Label, Verdict, expected_labels, score_rules

KEY_ACCRUED = ("amount_mismatch", "L-1", "accrued_interest")
KEY_PRICE = ("amount_mismatch", "L-1", "purchase_price")
KEY_MISSING = ("missing_record", "cp-q-2026-09-02", "L-2", "counterparty")


def _gt(**fields: object) -> str:
    record: dict[str, object] = {
        "batch_ids": ["cp-q-2026-09-02"],
        "loan_ids": ["L-1"],
        "fields": [],
        "missing_side": None,
        "wrong_side": "counterparty",
        "difficulty": "simple",
        "expected_proposal": "email",
    }
    record.update(fields)
    return json.dumps(record)


def test_expected_labels_expand_loans_times_fields_and_carry_the_cause() -> None:
    lines = [
        _gt(
            break_type="amount_mismatch",
            cause="rounding_difference",
            fields=["accrued_interest", "purchase_price"],
        ),
        _gt(
            break_type="missing_record",
            cause="loan_not_confirmed",
            missing_side="counterparty",
            loan_ids=["L-2"],
        ),
        _gt(
            break_type="stale_pending",
            cause="confirmation_overdue",
            wrong_side=None,
            loan_ids=["L-3"],
        ),
    ]

    labels = expected_labels(lines)

    rounding = Label("rounding_difference", "simple", "counterparty", "email")
    assert labels[KEY_ACCRUED] == rounding
    assert labels[KEY_PRICE] == rounding
    assert labels[KEY_MISSING].cause == "loan_not_confirmed"
    overdue = labels[("stale_pending", "cp-q-2026-09-02", "L-3", "counterparty")]
    assert overdue.wrong_side is None


def _labels() -> dict[tuple[str, ...], Label]:
    return {
        KEY_ACCRUED: Label("rounding_difference", "simple", "counterparty", "email"),
        KEY_PRICE: Label("rounding_difference", "simple", "counterparty", "email"),
        KEY_MISSING: Label("loan_not_confirmed", "simple", "counterparty", "email"),
        ("amount_mismatch", "L-9", "price_pct"): Label(
            "price_grid_amendment", "medium", "seller", "correction"
        ),
        ("amount_mismatch", "L-8", "price_pct"): Label(
            "dealer_wide_adjustment", "hard", "counterparty", "email"
        ),
    }


def test_s2_is_the_share_of_simple_breaks_explained_by_rules() -> None:
    verdicts = {
        KEY_ACCRUED: Verdict("rounding_difference", "counterparty", "email"),
        KEY_PRICE: Verdict("rounding_difference", "counterparty", "email"),
    }

    result = score_rules(_labels(), verdicts)

    assert result.by_difficulty["simple"].support == 3
    assert result.by_difficulty["simple"].explained == 2
    assert result.s2 == 2 / 3
    assert result.s3 == 0


def test_s3_counts_medium_and_hard_breaks_explained_by_any_rule() -> None:
    verdicts = {
        ("amount_mismatch", "L-9", "price_pct"): Verdict("rounding_difference", "seller", "email"),
        ("amount_mismatch", "L-8", "price_pct"): Verdict("rounding_difference", "seller", "email"),
    }

    result = score_rules(_labels(), verdicts)

    assert result.s3 == 2
    assert result.false_claims == (
        ("amount_mismatch", "L-8", "price_pct"),
        ("amount_mismatch", "L-9", "price_pct"),
    )


def test_accuracy_is_measured_among_explained_breaks_only() -> None:
    verdicts = {
        KEY_ACCRUED: Verdict("rounding_difference", "counterparty", "email"),
        KEY_PRICE: Verdict("accrual_start_alternative", "seller", "correction"),
    }

    result = score_rules(_labels(), verdicts)

    rounding = result.by_cause["rounding_difference"]
    assert (rounding.support, rounding.explained) == (2, 2)
    assert (rounding.cause_correct, rounding.wrong_side_correct, rounding.proposal_correct) == (
        1,
        1,
        1,
    )
    simple = result.by_difficulty["simple"]
    assert simple.cause_accuracy == 0.5
    assert simple.wrong_side_accuracy == 0.5
    assert simple.proposal_accuracy == 0.5


def test_a_verdict_for_an_unlabeled_break_is_not_scored_but_is_reported() -> None:
    verdicts = {("amount_mismatch", "L-77", "upb"): Verdict("x", None, "email")}

    result = score_rules(_labels(), verdicts)

    assert result.unlabeled_explained == (("amount_mismatch", "L-77", "upb"),)
    assert result.s2 == 0.0


def test_with_no_simple_breaks_s2_is_one() -> None:
    assert score_rules({}, {}).s2 == 1.0
