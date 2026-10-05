from datetime import date

from pydantic import BaseModel

from kredpare.core.canonical import Id, Money, Ratio
from kredpare.domains.lending.schemas._types import ROW_CONFIG, NonNegativeMoney, PositiveMoney


class PurchaseConfirmation(BaseModel):
    """Buyer file: one row per loan bought.

    purchase_price is deliberately not checked against the price formula: a buyer computing
    it differently is a break, not a validation error.
    """

    model_config = ROW_CONFIG

    loan_id: Id
    batch_id: Id
    settlement_date: date
    upb: PositiveMoney
    price_pct: Ratio
    accrued_interest: NonNegativeMoney
    purchase_price: Money
