from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from kredpare.domains.lending.pricing import DayCount, Rounding
from kredpare.domains.lending.schemas import FundedLoan
from kredpare.domains.lending.tools import calc_accrued_interest, recompute_purchase_price

# Both causes shift accrued_interest and, through it, purchase_price (see datagen inject.py).
_AMOUNT_FIELDS = ("accrued_interest", "purchase_price")
_ROUNDING_MAX_DELTA = Decimal("0.01")


@dataclass(frozen=True)
class RecomputeEvidence:
    """Why a rule explained a break: the recomputed values and every input used."""

    rule: str
    cause: str
    wrong_side: str
    proposal: str
    field: str
    seller_value: Decimal
    counterparty_value: Decimal
    recomputed_value: Decimal
    recomputed_accrued_interest: Decimal
    day_count: DayCount
    rounding: Rounding
    accrual_start: date
    accrual_end: date
    upb: Decimal
    note_rate: Decimal
    price_pct: Decimal


def _recompute(
    loan: FundedLoan,
    field: str,
    counterparty_value: Decimal,
    day_count: DayCount,
    *,
    rule: str,
    accrual_start: date,
    rounding: Rounding,
    max_delta: Decimal | None,
) -> RecomputeEvidence | None:
    if field not in _AMOUNT_FIELDS:
        return None
    seller_value = getattr(loan, field)
    if counterparty_value == seller_value:
        return None  # not a break
    if max_delta is not None and abs(counterparty_value - seller_value) > max_delta:
        return None
    accrued = calc_accrued_interest(
        loan.upb,
        loan.note_rate,
        accrual_start,
        loan.settlement_date,
        day_count,
        rounding=rounding,
    )
    recomputed = (
        accrued
        if field == "accrued_interest"
        else recompute_purchase_price(loan.upb, loan.price_pct, accrued)
    )
    if recomputed != counterparty_value:
        return None
    return RecomputeEvidence(
        rule=rule,
        cause=rule,
        wrong_side="counterparty",
        proposal="email",
        field=field,
        seller_value=seller_value,
        counterparty_value=counterparty_value,
        recomputed_value=recomputed,
        recomputed_accrued_interest=accrued,
        day_count=day_count,
        rounding=rounding,
        accrual_start=accrual_start,
        accrual_end=loan.settlement_date,
        upb=loan.upb,
        note_rate=loan.note_rate,
        price_pct=loan.price_pct,
    )


def rounding_difference(
    loan: FundedLoan, field: str, counterparty_value: Decimal, day_count: DayCount
) -> RecomputeEvidence | None:
    """Counterparty truncates accrued interest to cents instead of rounding half-up.

    Applies to amount_mismatch on accrued_interest or purchase_price with |delta| <= 0.01.
    Recomputes from the funding date with Rounding.TRUNCATE; explained only on an exact match.
    """
    return _recompute(
        loan,
        field,
        counterparty_value,
        day_count,
        rule="rounding_difference",
        accrual_start=loan.funding_date,
        rounding=Rounding.TRUNCATE,
        max_delta=_ROUNDING_MAX_DELTA,
    )


def accrual_start_alternative(
    loan: FundedLoan, field: str, counterparty_value: Decimal, day_count: DayCount
) -> RecomputeEvidence | None:
    """Counterparty accrues from the cut-off date instead of the funding date.

    Applies to amount_mismatch on accrued_interest or purchase_price. Recomputes half-up from
    cut_off_date; explained only on an exact match.
    """
    return _recompute(
        loan,
        field,
        counterparty_value,
        day_count,
        rule="accrual_start_alternative",
        accrual_start=loan.cut_off_date,
        rounding=Rounding.HALF_UP,
        max_delta=None,
    )
