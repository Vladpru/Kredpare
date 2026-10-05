from decimal import Decimal
from typing import Annotated

from pydantic import ConfigDict, Field

from kredpare.core.canonical import Id, Money

ROW_CONFIG = ConfigDict(strict=True, frozen=True, extra="forbid")

PositiveMoney = Annotated[Money, Field(gt=Decimal("0"))]
NonNegativeMoney = Annotated[Money, Field(ge=Decimal("0"))]
LoanId = Annotated[Id, Field(pattern=r"^L-\d{6}$")]
DealerId = Annotated[Id, Field(pattern=r"^D-\d{4}$")]
