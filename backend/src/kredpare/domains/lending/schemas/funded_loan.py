from datetime import date
from decimal import Decimal
from typing import Annotated, Literal, Self

from pydantic import BaseModel, Field, model_validator

from kredpare.core.canonical import Id, Money, Ratio, round_half_up_cents
from kredpare.domains.lending.schemas._types import (
    ROW_CONFIG,
    DealerId,
    LoanId,
    NonNegativeMoney,
    PositiveMoney,
)


class FundedLoan(BaseModel):
    """Seller file: one row per loan offered in a batch. Internally consistent by construction."""

    model_config = ROW_CONFIG

    loan_id: LoanId
    batch_id: Id
    dealer_id: DealerId
    credit_tier: Literal["A", "B", "C", "D"]
    funding_date: date
    cut_off_date: date
    settlement_date: date
    funded_amount: PositiveMoney
    upb: PositiveMoney
    note_rate: Annotated[Ratio, Field(gt=Decimal("0"), le=Decimal("0.36"))]
    term_months: Annotated[int, Field(ge=12, le=84)]
    price_pct: Ratio
    accrued_interest: NonNegativeMoney
    purchase_price: Money

    @model_validator(mode="after")
    def _check_consistency(self) -> Self:
        suffix = f"-{self.settlement_date.isoformat()}"
        if not self.batch_id.endswith(suffix) or self.batch_id == suffix:
            raise ValueError(f"batch_id must be '{{counterparty_id}}{suffix}', got {self.batch_id}")
        if self.funding_date > self.cut_off_date:
            raise ValueError("funding_date must not be after cut_off_date")
        if self.cut_off_date > self.settlement_date:
            raise ValueError("cut_off_date must not be after settlement_date")
        if self.upb > self.funded_amount:
            raise ValueError("upb must not exceed funded_amount")
        expected = round_half_up_cents(self.upb * self.price_pct) + self.accrued_interest
        if self.purchase_price != expected:
            raise ValueError(
                f"purchase_price {self.purchase_price} must equal "
                f"round_half_up(upb x price_pct, 2) + accrued_interest = {expected}"
            )
        return self
