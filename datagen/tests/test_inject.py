"""Injected data must differ from the seller exactly where ground truth says, and nowhere else."""

from collections import Counter
from datetime import date

from kredpare.domains.lending.pricing import DayCount, Rounding

from kredpare_datagen.agreements import BRACKWATER, QUILLMONT, ROUNDING_CITATION, TESSALINE
from kredpare_datagen.generate import Dataset, generate_clean, quote
from kredpare_datagen.ground_truth import GroundTruth
from kredpare_datagen.inject import inject
from tests.helpers import differences

Injected = tuple[Dataset, list[GroundTruth]]


def _by_cause(truth: list[GroundTruth]) -> dict[str, list[GroundTruth]]:
    result: dict[str, list[GroundTruth]] = {}
    for record in truth:
        result.setdefault(record.cause, []).append(record)
    return result


def test_every_cause_is_injected(injected: Injected) -> None:
    _, truth = injected

    assert set(_by_cause(truth)) == {
        "loan_not_confirmed",
        "loan_not_offered",
        "duplicate_row",
        "confirmation_overdue",
        "settlement_date_roll",
        "rounding_difference",
        "accrual_start_alternative",
        "accrued_interest_error",
        "price_grid_amendment",
        "dealer_wide_adjustment",
        "combined_causes",
        "unannounced_rule_change",
    }


def test_every_amount_and_date_difference_is_labeled_and_nothing_else(injected: Injected) -> None:
    dataset, truth = injected
    home = {f.loan_id: b.batch_id for b in dataset.batches for f in b.funded}
    labeled: dict[tuple[str, str], tuple[str, ...]] = {}
    for record in truth:
        if record.break_type in ("amount_mismatch", "date_mismatch"):
            for loan_id in record.loan_ids:
                assert home[loan_id] in record.batch_ids
                labeled[(home[loan_id], loan_id)] = record.fields
    actual = {
        (batch.batch_id, loan_id): fields
        for batch in dataset.batches
        for loan_id, fields in differences(batch).items()
    }

    assert actual == labeled


def test_one_cause_per_loan(injected: Injected) -> None:
    _, truth = injected
    loans = Counter(loan_id for record in truth for loan_id in record.loan_ids)

    assert [loan_id for loan_id, n in loans.items() if n > 1] == []


def test_missing_and_duplicate_rows_match_ground_truth(injected: Injected) -> None:
    dataset, truth = injected
    batches = {b.batch_id: b for b in dataset.batches}
    causes = _by_cause(truth)

    for record in causes["loan_not_confirmed"]:
        batch = batches[record.batch_ids[0]]
        assert batch.confirmation is not None
        assert record.loan_ids[0] not in {r.loan_id for r in batch.confirmation}
        assert (record.missing_side, record.wrong_side) == ("counterparty", "counterparty")
    for record in causes["loan_not_offered"]:
        batch = batches[record.batch_ids[0]]
        assert batch.confirmation is not None
        assert record.loan_ids[0] in {r.loan_id for r in batch.confirmation}
        assert record.loan_ids[0] not in {f.loan_id for f in batch.funded}
        assert record.missing_side == "seller"
    for record in causes["duplicate_row"]:
        batch = batches[record.batch_ids[0]]
        rows = batch.funded if record.wrong_side == "seller" else batch.confirmation or []
        assert [r.loan_id for r in rows].count(record.loan_ids[0]) == 2
        expected = "correction" if record.wrong_side == "seller" else "email"
        assert record.expected_proposal == expected


def test_confirmation_overdue_withholds_one_old_enough_file(injected: Injected) -> None:
    dataset, truth = injected
    overdue = _by_cause(truth)["confirmation_overdue"]
    withheld = [b for b in dataset.batches if b.confirmation is None]

    assert len(withheld) == 1
    assert {r.batch_ids for r in overdue} == {(withheld[0].batch_id,)}
    assert sorted(r.loan_ids[0] for r in overdue) == sorted(f.loan_id for f in withheld[0].funded)
    assert all(r.break_type == "stale_pending" and r.wrong_side is None for r in overdue)


def test_simple_causes_live_where_the_doc_puts_them(injected: Injected) -> None:
    _, truth = injected
    causes = _by_cause(truth)

    assert {r.counterparty_id for r in causes["settlement_date_roll"]} == {BRACKWATER}
    assert {r.batch_ids for r in causes["settlement_date_roll"]} == {("cp-brackwater-2026-08-17",)}
    assert {r.counterparty_id for r in causes["rounding_difference"]} == {BRACKWATER}
    assert {r.counterparty_id for r in causes["accrual_start_alternative"]} == {TESSALINE}
    for record in truth:
        if record.difficulty == "simple":
            assert (record.expected_level, record.expected_citations) == ("rule", ())


def test_rounding_difference_is_at_most_a_cent(injected: Injected) -> None:
    dataset, truth = injected
    loans = {f.loan_id: f for b in dataset.batches for f in b.funded}
    confirmed = {r.loan_id: r for b in dataset.batches for r in b.confirmation or []}

    for record in _by_cause(truth)["rounding_difference"]:
        loan_id = record.loan_ids[0]
        delta = loans[loan_id].accrued_interest - confirmed[loan_id].accrued_interest
        assert str(delta) == "0.01"


def test_medium_causes_cite_the_amendment_in_force(injected: Injected) -> None:
    _, truth = injected
    causes = _by_cause(truth)

    assert {r.expected_citations for r in causes["accrued_interest_error"]} == {
        ("amendment-1 §4.2",)
    }
    assert {r.batch_ids for r in causes["accrued_interest_error"]} == {
        ("cp-brackwater-2026-08-31",)
    }
    assert {(r.counterparty_id, r.expected_citations) for r in causes["price_grid_amendment"]} == {
        (QUILLMONT, ("amendment-2 §4.1",)),
        (TESSALINE, ("amendment-1 §4.1",)),
    }
    for record in causes["accrued_interest_error"] + causes["price_grid_amendment"]:
        assert (record.difficulty, record.expected_level) == ("medium", "workflow")
        expected = "correction" if record.wrong_side == "seller" else "email"
        assert record.expected_proposal == expected


def test_price_grid_amendment_covers_every_amended_tier_loan(injected: Injected) -> None:
    dataset, truth = injected
    labeled = {loan for r in _by_cause(truth)["price_grid_amendment"] for loan in r.loan_ids}
    amended = {
        f.loan_id
        for b in dataset.batches
        for f in b.funded
        if (
            (b.counterparty_id, f.credit_tier) == (QUILLMONT, "B")
            and b.settlement_date >= date(2026, 9, 1)
        )
        or (
            (b.counterparty_id, f.credit_tier) == (TESSALINE, "C")
            and b.settlement_date >= date(2026, 8, 24)
        )
    }

    assert labeled == amended


def _single(truth: list[GroundTruth], cause: str) -> GroundTruth:
    records = _by_cause(truth)[cause]
    assert len(records) == 1
    record = records[0]
    assert (record.difficulty, record.expected_level) == ("hard", "agent")
    assert len(record.loan_ids) >= 2
    return record


def test_dealer_wide_adjustment_hits_every_loan_of_one_dealer_in_one_batch(
    injected: Injected,
) -> None:
    dataset, truth = injected
    record = _single(truth, "dealer_wide_adjustment")
    (batch,) = [b for b in dataset.batches if b.batch_id in record.batch_ids]
    dealers = {f.dealer_id for f in batch.funded if f.loan_id in record.loan_ids}

    assert batch.counterparty_id == TESSALINE
    assert len(dealers) == 1
    assert {f.loan_id for f in batch.funded if f.dealer_id in dealers} == set(record.loan_ids)
    assert record.fields == ("price_pct", "purchase_price")


def test_unannounced_change_spans_quillmont_batches_from_08_26(injected: Injected) -> None:
    dataset, truth = injected
    record = _single(truth, "unannounced_rule_change")
    later = [
        b
        for b in dataset.batches
        if b.counterparty_id == QUILLMONT and b.settlement_date >= date(2026, 8, 26)
    ]
    amended = {
        f.loan_id
        for b in later
        for f in b.funded
        if f.credit_tier == "B" and b.settlement_date >= date(2026, 9, 1)
    }

    assert record.batch_ids == tuple(b.batch_id for b in later)
    assert set(record.loan_ids) == {f.loan_id for b in later for f in b.funded} - amended
    assert record.expected_citations == ("base §4.2",)


def test_combined_causes_leave_a_residual_for_each_single_cause(injected: Injected) -> None:
    dataset, truth = injected
    record = _single(truth, "combined_causes")
    (batch,) = [b for b in dataset.batches if b.batch_id in record.batch_ids]
    confirmed = {r.loan_id: r for r in batch.confirmation or []}

    assert batch.counterparty_id == BRACKWATER
    assert record.expected_citations == ("amendment-1 §4.2", ROUNDING_CITATION)
    for loan in batch.funded:
        if loan.loan_id not in record.loan_ids:
            continue
        reported = confirmed[loan.loan_id].accrued_interest
        old_day_count, _ = quote(loan, price_pct=loan.price_pct, day_count=DayCount.THIRTY_360)
        truncated, _ = quote(
            loan,
            price_pct=loan.price_pct,
            day_count=DayCount.ACTUAL_365,
            rounding=Rounding.TRUNCATE,
        )
        assert reported not in (loan.accrued_interest, old_day_count, truncated)


def test_inject_does_not_mutate_the_clean_dataset(clean: Dataset, injected: Injected) -> None:
    assert clean == generate_clean(seed=42, start=clean.start, days=30)
    assert injected[0] != clean


def test_injection_is_deterministic(clean: Dataset, injected: Injected) -> None:
    assert inject(clean) == injected


def test_break_ids_are_sequential(injected: Injected) -> None:
    _, truth = injected

    assert [r.break_id for r in truth] == [f"gt-{n:06d}" for n in range(1, len(truth) + 1)]


def test_onboarding_follows_the_injected_confirmations(injected: Injected) -> None:
    dataset, _ = injected
    confirmed = {r.loan_id for b in dataset.batches for r in b.confirmation or []}

    assert {o.loan_id for o in dataset.onboardings} <= confirmed
