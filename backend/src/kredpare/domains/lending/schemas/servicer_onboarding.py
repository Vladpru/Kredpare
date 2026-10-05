from datetime import date
from typing import Self

from pydantic import BaseModel, model_validator

from kredpare.core.canonical import Id
from kredpare.domains.lending.schemas._types import ROW_CONFIG, PositiveMoney


class ServicerOnboarding(BaseModel):
    """Servicer file: one row per boarded loan.

    boarded_date >= settlement_date spans two files, so matching checks it, not this row.
    """

    model_config = ROW_CONFIG

    loan_id: Id
    boarded_date: date
    upb: PositiveMoney
    next_payment_due_date: date

    @model_validator(mode="after")
    def _check_dates(self) -> Self:
        if self.next_payment_due_date <= self.boarded_date:
            raise ValueError("next_payment_due_date must be after boarded_date")
        return self
