"""Rules for amount mismatches, built over the pure recomputations in _recompute.

Rules never read an agreement, so the day-count convention is inferred from the seller record:
a convention is a candidate only if it reproduces the seller's own accrued interest exactly.
A rule explains only when a candidate also reproduces the counterparty value exactly. Where no
candidate does, the loan needs an agreement (an amendment) or two causes are stacked, and the
rule stays silent for the workflow and agent.
"""

from collections.abc import Callable
from decimal import Decimal, InvalidOperation

from kredpare.core.rules.types import BreakView, Explanation, JsonValue, RuleContext
from kredpare.domains.lending.pricing import DayCount, Rounding
from kredpare.domains.lending.rules._common import SELLER_SCHEMA
from kredpare.domains.lending.rules._recompute import (
    RecomputeEvidence,
    accrual_start_alternative,
    rounding_difference,
)
from kredpare.domains.lending.schemas import FundedLoan
from kredpare.domains.lending.tools import calc_accrued_interest

Recompute = Callable[[FundedLoan, str, Decimal, DayCount], RecomputeEvidence | None]


def candidate_conventions(loan: FundedLoan) -> tuple[DayCount, ...]:
    """Conventions under which half-up accrual from the funding date gives the seller's value."""
    return tuple(
        convention
        for convention in DayCount
        if calc_accrued_interest(
            loan.upb,
            loan.note_rate,
            loan.funding_date,
            loan.settlement_date,
            convention,
            rounding=Rounding.HALF_UP,
        )
        == loan.accrued_interest
    )


def _explain(
    rule: str, recompute: Recompute, brk: BreakView, context: RuleContext
) -> Explanation | None:
    if brk.field is None or brk.left_value is None or brk.right_value is None:
        return None
    seller_record = context.record(brk.left_record_id)
    if (
        seller_record is None
        or seller_record.schema_name != SELLER_SCHEMA
        or context.record(brk.right_record_id) is None
    ):
        return None
    try:
        loan = FundedLoan.model_validate(seller_record.data, strict=False)
        seller_value, counterparty_value = Decimal(brk.left_value), Decimal(brk.right_value)
    except (ValueError, InvalidOperation):
        return None
    if brk.field not in ("accrued_interest", "purchase_price"):
        return None
    if getattr(loan, brk.field) != seller_value:
        return None

    candidates = candidate_conventions(loan)
    reproducing = [
        found
        for convention in candidates
        if (found := recompute(loan, brk.field, counterparty_value, convention)) is not None
    ]
    if not reproducing:
        return None
    first = reproducing[0]
    evidence: dict[str, JsonValue] = {
        "field": first.field,
        "seller_value": str(first.seller_value),
        "counterparty_value": str(first.counterparty_value),
        "recomputed_value": str(first.recomputed_value),
        "recomputed_accrued_interest": str(first.recomputed_accrued_interest),
        "day_count": first.day_count.value,
        "day_count_candidates": [c.value for c in candidates],
        "rounding": first.rounding.value,
        "accrual_start": first.accrual_start.isoformat(),
        "accrual_end": first.accrual_end.isoformat(),
        "upb": str(first.upb),
        "note_rate": str(first.note_rate),
        "price_pct": str(first.price_pct),
    }
    return Explanation(
        rule=rule,
        cause=first.cause,
        wrong_side="counterparty" if first.wrong_side == "counterparty" else "seller",
        proposal="email" if first.proposal == "email" else "correction",
        evidence=evidence,
    )


class RoundingDifference:
    """The counterparty truncates accrued interest to cents instead of rounding half-up."""

    name = "rounding_difference"
    break_types = ("amount_mismatch",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        return _explain(self.name, rounding_difference, brk, context)


class AccrualStartAlternative:
    """The counterparty accrues from the cut-off date instead of the funding date."""

    name = "accrual_start_alternative"
    break_types = ("amount_mismatch",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        return _explain(self.name, accrual_start_alternative, brk, context)
