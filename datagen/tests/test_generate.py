from collections import Counter
from datetime import date

from kredpare.domains.lending.pricing import accrued_interest, purchase_price

from kredpare_datagen.agreements import BUYERS, cut_off_date, terms_in_force
from kredpare_datagen.generate import Dataset, generate_clean

WINDOW_START = date(2026, 8, 10)


def test_window_is_inclusive_of_both_ends(clean: Dataset) -> None:
    assert (clean.start, clean.end) == (WINDOW_START, date(2026, 9, 8))


def test_one_batch_per_buyer_settlement(clean: Dataset) -> None:
    per_buyer = Counter(b.counterparty_id for b in clean.batches)

    assert per_buyer == {"cp-quillmont": 4, "cp-brackwater": 2, "cp-tessaline": 4}
    assert all(len(b.funded) == 40 for b in clean.batches)


def test_batch_ids_and_dates(clean: Dataset) -> None:
    for batch in clean.batches:
        assert batch.batch_id == f"{batch.counterparty_id}-{batch.settlement_date.isoformat()}"
        assert batch.cut_off_date == cut_off_date(batch.settlement_date)
        for loan in batch.funded:
            assert loan.batch_id == batch.batch_id
            assert loan.settlement_date == batch.settlement_date
            assert loan.cut_off_date == batch.cut_off_date
            assert loan.funding_date <= batch.cut_off_date


def test_loan_ids_are_unique_across_batches(clean: Dataset) -> None:
    ids = [loan.loan_id for b in clean.batches for loan in b.funded]

    assert len(ids) == len(set(ids)) == 400


def test_every_batch_has_every_tier(clean: Dataset) -> None:
    for batch in clean.batches:
        assert {loan.credit_tier for loan in batch.funded} == set("ABCD")


def test_seller_values_follow_the_agreement_in_force(clean: Dataset) -> None:
    for batch in clean.batches:
        terms = terms_in_force(batch.counterparty_id, batch.settlement_date)
        for loan in batch.funded:
            accrued = accrued_interest(
                loan.upb, loan.note_rate, loan.funding_date, loan.settlement_date, terms.day_count
            )
            assert loan.price_pct == terms.pricing_grid[loan.credit_tier]
            assert loan.accrued_interest == accrued
            assert loan.purchase_price == purchase_price(loan.upb, loan.price_pct, accrued)
            assert loan.upb == loan.funded_amount


def test_clean_confirmation_matches_the_seller(clean: Dataset) -> None:
    for batch in clean.batches:
        assert batch.confirmation is not None
        assert [
            (
                c.loan_id,
                c.batch_id,
                c.settlement_date,
                c.upb,
                c.price_pct,
                c.accrued_interest,
                c.purchase_price,
            )
            for c in batch.confirmation
        ] == [
            (
                f.loan_id,
                f.batch_id,
                f.settlement_date,
                f.upb,
                f.price_pct,
                f.accrued_interest,
                f.purchase_price,
            )
            for f in batch.funded
        ]


def test_servicer_boards_confirmed_loans_inside_the_window(clean: Dataset) -> None:
    settled = {f.loan_id: f for b in clean.batches for f in b.funded}
    boarded = [o.loan_id for o in clean.onboardings]

    assert len(boarded) == len(set(boarded)) > 0
    for row in clean.onboardings:
        loan = settled[row.loan_id]
        assert loan.settlement_date < row.boarded_date <= clean.end
        assert row.upb == loan.upb
    # Loans settled early in the window are all boarded by its end.
    first = clean.batches[0]
    assert {f.loan_id for f in first.funded} <= set(boarded)


def test_same_seed_same_data_and_different_seed_different_data(clean: Dataset) -> None:
    assert generate_clean(seed=42, start=WINDOW_START, days=30) == clean
    assert generate_clean(seed=7, start=WINDOW_START, days=30) != clean


def test_buyers_order_is_stable(clean: Dataset) -> None:
    order = [(b.settlement_date, BUYERS.index(b.counterparty_id)) for b in clean.batches]

    assert order == sorted(order)
