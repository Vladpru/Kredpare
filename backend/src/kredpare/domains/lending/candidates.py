"""Candidate values for a mismatched field, computed with pricing.py only.

The workflow model never computes an amount. It chooses among these candidates and cites the
clause. Every parameter combination and every pricing grid version in the documents becomes a
candidate, whichever version is in force: that choice is the model's, and the eval measures it.

`supported_by` lists the clauses that state exactly the candidate's parameters. A combination no
clause states (inclusive end, accrual from the cut-off date, truncation) has none, so a value
only such a candidate reproduces cannot be explained by the agreements.
"""

import itertools
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from kredpare.domains.lending.agreement_documents import (
    AgreementDocument,
    PricingGrid,
    parse_pricing_grid,
    parse_sections,
)
from kredpare.domains.lending.pricing import (
    DayCount,
    Rounding,
    accrued_interest,
    purchase_price,
)

# Terms every agreement states in sections 4.2 and 4.3: accrue from the funding date to the
# settlement date (exclusive), round half-up per loan. Only the day count varies by document.
_CONTRACTUAL = ("end_exclusive", "from_funding", Rounding.HALF_UP)
_DAY_COUNT_IN_TEXT = {DayCount.ACTUAL_365: "Actual/365", DayCount.THIRTY_360: "30/360"}
_ACCRUAL_TITLE = re.compile(r"accrued interest", re.IGNORECASE)


@dataclass(frozen=True)
class LoanTerms:
    upb: Decimal
    note_rate: Decimal
    funding_date: date
    cut_off_date: date
    settlement_date: date
    credit_tier: str


@dataclass(frozen=True)
class Candidate:
    id: str
    field: str
    value: Decimal
    parameters: dict[str, str]
    supported_by: list[str]
    reproduces_counterparty_value: bool
    reproduces_company_value: bool

    def to_json(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "field": self.field,
            "value": str(self.value),
            "parameters": self.parameters,
            "supported_by": self.supported_by,
            "reproduces_counterparty_value": self.reproduces_counterparty_value,
            "reproduces_company_value": self.reproduces_company_value,
        }


@dataclass(frozen=True)
class _Accrual:
    day_count: DayCount
    end_inclusive: bool
    from_cut_off: bool
    rounding: Rounding

    @property
    def id(self) -> str:
        return "|".join(
            (
                self.day_count.value,
                "end_inclusive" if self.end_inclusive else "end_exclusive",
                "from_cut_off" if self.from_cut_off else "from_funding",
                self.rounding.value,
            )
        )

    @property
    def parameters(self) -> dict[str, str]:
        return {
            "day_count": self.day_count.value,
            "end": "inclusive" if self.end_inclusive else "exclusive",
            "accrual_start": "cut_off_date" if self.from_cut_off else "funding_date",
            "rounding": self.rounding.value,
        }

    @property
    def is_contractual(self) -> bool:
        return (
            "end_inclusive" if self.end_inclusive else "end_exclusive",
            "from_cut_off" if self.from_cut_off else "from_funding",
            self.rounding,
        ) == _CONTRACTUAL

    def value(self, loan: LoanTerms) -> Decimal:
        return accrued_interest(
            loan.upb,
            loan.note_rate,
            loan.cut_off_date if self.from_cut_off else loan.funding_date,
            loan.settlement_date,
            self.day_count,
            end_inclusive=self.end_inclusive,
            rounding=self.rounding,
        )


def _accruals() -> list[_Accrual]:
    return [
        _Accrual(day_count, inclusive, cut_off, rounding)
        for day_count, inclusive, cut_off, rounding in itertools.product(
            DayCount, (False, True), (False, True), Rounding
        )
    ]


def _accrual_clauses(documents: list[AgreementDocument]) -> dict[DayCount, list[str]]:
    """Citations of the accrued interest sections, by the day count each one states."""
    found: dict[DayCount, list[str]] = {day_count: [] for day_count in DayCount}
    for document in documents:
        for section in parse_sections(document.body).values():
            if not _ACCRUAL_TITLE.search(section.title):
                continue
            for day_count, token in _DAY_COUNT_IN_TEXT.items():
                if token in section.text:
                    found[day_count].append(f"{document.document} §{section.number}")
    return found


def _support(accrual: _Accrual, clauses: dict[DayCount, list[str]]) -> list[str]:
    return list(clauses[accrual.day_count]) if accrual.is_contractual else []


def build_candidates(
    field: str,
    loan: LoanTerms,
    documents: list[AgreementDocument],
    company_value: Decimal,
    counterparty_value: Decimal,
) -> list[Candidate]:
    """Candidates for `field`; empty when the field is not one the agreements govern."""
    clauses = _accrual_clauses(documents)
    grids = [g for d in documents if (g := parse_pricing_grid(d)) is not None]

    def make(
        id_: str, value: Decimal, parameters: dict[str, str], supported_by: list[str]
    ) -> Candidate:
        return Candidate(
            id=id_,
            field=field,
            value=value,
            parameters=parameters,
            supported_by=supported_by,
            reproduces_counterparty_value=value == counterparty_value,
            reproduces_company_value=value == company_value,
        )

    if field == "accrued_interest":
        return [make(a.id, a.value(loan), a.parameters, _support(a, clauses)) for a in _accruals()]
    if field == "price_pct":
        return [
            make(f"grid:{g.source}", *_price(g, loan))
            for g in grids
            if loan.credit_tier in g.prices
        ]
    if field == "purchase_price":
        candidates = [
            make(
                f"grid:{g.source}|{a.id}",
                purchase_price(loan.upb, g.prices[loan.credit_tier], a.value(loan)),
                {**_price(g, loan)[1], **a.parameters},
                [g.source, *support] if (support := _support(a, clauses)) else [],
            )
            for g in grids
            if loan.credit_tier in g.prices
            for a in _accruals()
        ]
        return [
            c for c in candidates if c.reproduces_counterparty_value or c.reproduces_company_value
        ]
    return []


def _price(grid: PricingGrid, loan: LoanTerms) -> tuple[Decimal, dict[str, str], list[str]]:
    return (
        grid.prices[loan.credit_tier],
        {
            "credit_tier": loan.credit_tier,
            "grid_source": grid.source,
            "grid_effective_date": grid.effective_date.isoformat(),
        },
        [grid.source],
    )
