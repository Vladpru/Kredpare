from datetime import date
from decimal import Decimal

from kredpare.domains.lending.agreement_documents import load_agreements
from kredpare.domains.lending.candidates import Candidate, LoanTerms, build_candidates
from kredpare.domains.lending.pricing import (
    DayCount,
    Rounding,
    accrued_interest,
    purchase_price,
)

LOAN = LoanTerms(
    upb=Decimal("20000.00"),
    note_rate=Decimal("0.089900"),
    funding_date=date(2026, 7, 20),
    cut_off_date=date(2026, 8, 27),
    settlement_date=date(2026, 8, 31),
    credit_tier="B",
)


def _accrued(day_count: DayCount, **kwargs: object) -> Decimal:
    return accrued_interest(
        LOAN.upb,
        LOAN.note_rate,
        kwargs.pop("start", LOAN.funding_date),  # type: ignore[arg-type]
        LOAN.settlement_date,
        day_count,
        **kwargs,  # type: ignore[arg-type]
    )


def _by_id(candidates: list[Candidate]) -> dict[str, Candidate]:
    return {c.id: c for c in candidates}


def test_accrued_interest_candidates_cover_every_parameter_combination() -> None:
    docs = load_agreements("cp-brackwater")
    company, counterparty = _accrued(DayCount.ACTUAL_365), _accrued(DayCount.THIRTY_360)
    assert company != counterparty

    candidates = build_candidates("accrued_interest", LOAN, docs, company, counterparty)

    assert len(candidates) == 2 * 2 * 2 * 2
    assert len({c.id for c in candidates}) == 16
    by_id = _by_id(candidates)
    old = by_id["30/360|end_exclusive|from_funding|half_up"]
    new = by_id["actual/365|end_exclusive|from_funding|half_up"]
    assert old.value == counterparty and old.reproduces_counterparty_value
    assert not old.reproduces_company_value
    assert new.value == company and new.reproduces_company_value
    assert old.parameters == {
        "day_count": "30/360",
        "end": "exclusive",
        "accrual_start": "funding_date",
        "rounding": "half_up",
    }


def test_candidate_values_come_from_pricing_module() -> None:
    docs = load_agreements("cp-brackwater")
    candidates = build_candidates("accrued_interest", LOAN, docs, Decimal("0"), Decimal("0"))

    by_id = _by_id(candidates)
    assert by_id["30/360|end_inclusive|from_cut_off|truncate"].value == _accrued(
        DayCount.THIRTY_360,
        start=LOAN.cut_off_date,
        end_inclusive=True,
        rounding=Rounding.TRUNCATE,
    )


def test_clause_support_names_the_clauses_stating_the_day_count_not_the_one_in_force() -> None:
    docs = load_agreements("cp-brackwater")
    candidates = _by_id(build_candidates("accrued_interest", LOAN, docs, Decimal(0), Decimal(0)))

    assert candidates["30/360|end_exclusive|from_funding|half_up"].supported_by == ["base §4.2"]
    assert candidates["actual/365|end_exclusive|from_funding|half_up"].supported_by == [
        "amendment-1 §4.2"
    ]


def test_parameters_no_agreement_allows_have_no_clause_support() -> None:
    docs = load_agreements("cp-quillmont")
    candidates = build_candidates("accrued_interest", LOAN, docs, Decimal(0), Decimal(0))

    supported = {c.id for c in candidates if c.supported_by}
    assert supported == {"actual/365|end_exclusive|from_funding|half_up"}
    inclusive = _by_id(candidates)["actual/365|end_inclusive|from_funding|half_up"]
    assert inclusive.supported_by == []


def test_price_pct_candidates_one_per_grid_version_with_source() -> None:
    docs = load_agreements("cp-quillmont")
    company, counterparty = Decimal("1.0100"), Decimal("1.0150")

    candidates = build_candidates("price_pct", LOAN, docs, company, counterparty)

    by_id = _by_id(candidates)
    assert set(by_id) == {"grid:base §4.1", "grid:amendment-2 §4.1"}
    old, new = by_id["grid:base §4.1"], by_id["grid:amendment-2 §4.1"]
    assert (old.value, new.value) == (Decimal("1.0150"), Decimal("1.0100"))
    assert old.reproduces_counterparty_value and not old.reproduces_company_value
    assert new.reproduces_company_value and not new.reproduces_counterparty_value
    assert new.supported_by == ["amendment-2 §4.1"]
    assert new.parameters["grid_effective_date"] == "2026-09-01"
    assert new.parameters["credit_tier"] == "B"


def test_purchase_price_candidates_keep_only_those_reproducing_a_value() -> None:
    docs = load_agreements("cp-quillmont")
    accrued = _accrued(DayCount.ACTUAL_365)
    company = purchase_price(LOAN.upb, Decimal("1.0100"), accrued)
    counterparty = purchase_price(LOAN.upb, Decimal("1.0150"), accrued)

    candidates = build_candidates("purchase_price", LOAN, docs, company, counterparty)

    assert candidates
    assert all(c.reproduces_company_value or c.reproduces_counterparty_value for c in candidates)
    old = [
        c
        for c in candidates
        if c.reproduces_counterparty_value and c.parameters["grid_source"] == "base §4.1"
    ]
    assert old
    assert any(
        c.id.startswith("grid:base §4.1|actual/365|end_exclusive|from_funding|half_up")
        and c.supported_by == ["base §4.1", "base §4.2"]
        for c in old
    )


def test_inclusive_end_candidate_reproduces_value_but_has_no_clause() -> None:
    docs = load_agreements("cp-quillmont")
    counterparty = _accrued(DayCount.ACTUAL_365, end_inclusive=True)
    company = _accrued(DayCount.ACTUAL_365)

    candidates = build_candidates("accrued_interest", LOAN, docs, company, counterparty)

    reproducing = [c for c in candidates if c.reproduces_counterparty_value]
    assert reproducing
    assert all(not c.supported_by for c in reproducing)


def test_unsupported_field_has_no_candidates() -> None:
    docs = load_agreements("cp-quillmont")
    assert build_candidates("settlement_date", LOAN, docs, Decimal(0), Decimal(0)) == []


def test_to_json_is_json_safe() -> None:
    import json

    docs = load_agreements("cp-quillmont")
    candidate = build_candidates("price_pct", LOAN, docs, Decimal("1"), Decimal("1"))[0]
    data = candidate.to_json()
    assert json.loads(json.dumps(data)) == data
    assert data["value"] == str(candidate.value)
