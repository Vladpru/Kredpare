"""Iteration 1 DoD: the generator is trustworthy as an eval source, for any seed and window."""

import io
from collections import Counter
from datetime import date
from decimal import Decimal
from pathlib import Path

import polars as pl
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from kredpare.domains.lending.schemas import FundedLoan
from kredpare.domains.lending.spec import LENDING

from kredpare_datagen.cli import main
from kredpare_datagen.formats import render_funded
from kredpare_datagen.generate import Dataset, generate_clean
from kredpare_datagen.ground_truth import GroundTruth
from kredpare_datagen.inject import inject
from tests.helpers import differences

PROPERTY_SETTINGS = settings(
    max_examples=30, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)

seeds = st.integers(min_value=0, max_value=2**32 - 1)
starts = st.dates(min_value=date(2026, 7, 1), max_value=date(2026, 10, 31))
window_days = st.integers(min_value=10, max_value=45)
batch_sizes = st.integers(min_value=4, max_value=40)


def _anomalies(dataset: Dataset) -> set[tuple[str, ...]]:
    """Everything a reconciliation could notice, derived from the data alone."""
    found: set[tuple[str, ...]] = set()
    for batch in dataset.batches:
        for loan_id, fields in differences(batch).items():
            found.add(("difference", batch.batch_id, loan_id, *fields))
        seller = [f.loan_id for f in batch.funded]
        for loan_id, count in Counter(seller).items():
            if count > 1:
                found.add(("duplicate", batch.batch_id, loan_id, "seller"))
        if batch.confirmation is None:
            found.update(("withheld", batch.batch_id, loan_id) for loan_id in seller)
            continue
        confirmed = [r.loan_id for r in batch.confirmation]
        for loan_id, count in Counter(confirmed).items():
            if count > 1:
                found.add(("duplicate", batch.batch_id, loan_id, "counterparty"))
        found.update(("unconfirmed", batch.batch_id, i) for i in set(seller) - set(confirmed))
        found.update(("unoffered", batch.batch_id, i) for i in set(confirmed) - set(seller))
    return found


def _labeled(dataset: Dataset, truth: list[GroundTruth]) -> set[tuple[str, ...]]:
    home = {f.loan_id: b.batch_id for b in dataset.batches for f in b.funded}
    labeled: set[tuple[str, ...]] = set()
    for record in truth:
        batch_id = record.batch_ids[0]
        loan_id = record.loan_ids[0]
        match record.break_type:
            case "amount_mismatch" | "date_mismatch":
                labeled.update(
                    ("difference", home[loan], loan, *record.fields) for loan in record.loan_ids
                )
            case "duplicate":
                labeled.add(("duplicate", batch_id, loan_id, str(record.wrong_side)))
            case "stale_pending":
                labeled.add(("withheld", batch_id, loan_id))
            case "missing_record" if record.missing_side == "counterparty":
                labeled.add(("unconfirmed", batch_id, loan_id))
            case "missing_record":
                labeled.add(("unoffered", batch_id, loan_id))
    return labeled


@PROPERTY_SETTINGS
@given(seed=seeds, start=starts, days=window_days, size=batch_sizes)
def test_every_injected_break_is_in_ground_truth_and_nothing_else(
    seed: int, start: date, days: int, size: int
) -> None:
    dataset, truth = inject(generate_clean(seed, start, days, size))

    assert _anomalies(dataset) == _labeled(dataset, truth)
    loans = Counter(loan for record in truth for loan in record.loan_ids)
    assert [loan for loan, n in loans.items() if n > 1] == []


@PROPERTY_SETTINGS
@given(seed=seeds, start=starts, days=window_days, size=batch_sizes)
def test_clean_data_has_no_anomalies(seed: int, start: date, days: int, size: int) -> None:
    assert _anomalies(generate_clean(seed, start, days, size)) == set()


_DATES = {"funding_date", "cut_off_date", "settlement_date"}
_DECIMALS = {"funded_amount", "upb", "note_rate", "price_pct", "accrued_interest", "purchase_price"}


def _read_seller_csv(text: str) -> pl.DataFrame:
    """Parse the canonical seller format back into canonical Python values."""
    raw = pl.read_csv(io.StringIO(text), infer_schema=False)
    rows: list[dict[str, object]] = []
    for row in raw.to_dicts():
        parsed: dict[str, object] = {}
        for name, value in row.items():
            assert isinstance(value, str)
            if name in _DATES:
                parsed[name] = date.fromisoformat(value)
            elif name in _DECIMALS:
                parsed[name] = Decimal(value)
            elif name == "term_months":
                parsed[name] = int(value)
            else:
                parsed[name] = value
        rows.append(parsed)
    return pl.DataFrame(rows)


def _assert_valid(dataset: Dataset) -> None:
    for batch in dataset.batches:
        seller = LENDING.schema("FundedLoan").validate_frame(
            _read_seller_csv(render_funded(batch.funded))
        )
        assert seller.errors == ()
        assert list(seller.rows) == batch.funded
        if batch.confirmation is not None:
            frame = pl.DataFrame([r.model_dump() for r in batch.confirmation])
            assert LENDING.schema("PurchaseConfirmation").validate_frame(frame).errors == ()
    if dataset.onboardings:
        frame = pl.DataFrame([o.model_dump() for o in dataset.onboardings])
        assert LENDING.schema("ServicerOnboarding").validate_frame(frame).errors == ()


@PROPERTY_SETTINGS
@given(seed=seeds, start=starts, days=window_days, size=batch_sizes)
def test_clean_data_passes_schema_validation(seed: int, start: date, days: int, size: int) -> None:
    _assert_valid(generate_clean(seed, start, days, size))


@PROPERTY_SETTINGS
@given(seed=seeds, start=starts, days=window_days, size=batch_sizes)
def test_injected_data_still_passes_schema_validation(
    seed: int, start: date, days: int, size: int
) -> None:
    # Breaks come from valid records only; injection never produces an invalid row.
    _assert_valid(inject(generate_clean(seed, start, days, size))[0])


def _snapshot(directory: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


@settings(max_examples=5, deadline=None)
@given(seed=seeds)
def test_same_seed_produces_byte_identical_output(
    seed: int, tmp_path_factory: pytest.TempPathFactory
) -> None:
    first, second = tmp_path_factory.mktemp("first"), tmp_path_factory.mktemp("second")
    for out in (first, second):
        assert main(["--seed", str(seed), "--out", str(out)]) == 0

    assert _snapshot(first) == _snapshot(second)
    assert FundedLoan.__name__ in (first / "manifest.jsonl").read_text()


def test_different_seeds_produce_different_output(tmp_path: Path) -> None:
    for seed in ("1", "2"):
        main(["--seed", seed, "--out", str(tmp_path / seed)])

    assert _snapshot(tmp_path / "1") != _snapshot(tmp_path / "2")
