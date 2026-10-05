"""Clean synthetic data: every party agrees on every loan. Injectors add breaks afterwards."""

import random
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from kredpare.domains.lending.pricing import DayCount, Rounding, accrued_interest, purchase_price
from kredpare.domains.lending.schemas import (
    FundedLoan,
    PurchaseConfirmation,
    ServicerOnboarding,
)

from kredpare_datagen.agreements import (
    BUYERS,
    TIERS,
    Settlement,
    Tier,
    cut_off_date,
    settlements,
    terms_in_force,
)
from kredpare_datagen.calendar import add_business_days

DEALERS = tuple(f"D-{n:04d}" for n in range(101, 109))
_TIER_WEIGHTS = (30, 35, 25, 10)
_TERMS_MONTHS = (36, 48, 60, 72, 84)


@dataclass
class Batch:
    counterparty_id: str
    settlement: Settlement
    funded: list[FundedLoan]
    """Seller file rows, in file order."""
    confirmation: list[PurchaseConfirmation] | None
    """Buyer file rows in file order; None when the file has not been received."""

    @property
    def settlement_date(self) -> date:
        return self.settlement.settlement_date

    @property
    def cut_off_date(self) -> date:
        return cut_off_date(self.settlement_date)

    @property
    def batch_id(self) -> str:
        return f"{self.counterparty_id}-{self.settlement_date.isoformat()}"


@dataclass
class Dataset:
    seed: int
    start: date
    end: date
    """Last day of the window, also the as-of date for ageing."""
    batches: list[Batch]
    onboardings: list[ServicerOnboarding]


def quote(
    loan: FundedLoan,
    *,
    price_pct: Decimal,
    day_count: DayCount,
    accrual_start: date | None = None,
    settlement_date: date | None = None,
    end_inclusive: bool = False,
    rounding: Rounding = Rounding.HALF_UP,
) -> tuple[Decimal, Decimal]:
    """(accrued_interest, purchase_price) for a loan under the given calculation choices."""
    accrued = accrued_interest(
        loan.upb,
        loan.note_rate,
        accrual_start or loan.funding_date,
        settlement_date or loan.settlement_date,
        day_count,
        end_inclusive=end_inclusive,
        rounding=rounding,
    )
    return accrued, purchase_price(loan.upb, price_pct, accrued)


def confirm(loan: FundedLoan) -> PurchaseConfirmation:
    """What a buyer that agrees with the seller sends back."""
    return PurchaseConfirmation(
        loan_id=loan.loan_id,
        batch_id=loan.batch_id,
        settlement_date=loan.settlement_date,
        upb=loan.upb,
        price_pct=loan.price_pct,
        accrued_interest=loan.accrued_interest,
        purchase_price=loan.purchase_price,
    )


def generate_clean(seed: int, start: date, days: int, loans_per_batch: int = 40) -> Dataset:
    rng = random.Random(seed)
    end = start + timedelta(days=days - 1)
    planned = sorted(
        ((s, buyer) for buyer in BUYERS for s in settlements(buyer, start, end)),
        key=lambda item: (item[0].settlement_date, BUYERS.index(item[1])),
    )
    batches: list[Batch] = []
    next_loan = 1
    for settlement, buyer in planned:
        batch = Batch(buyer, settlement, [], None)
        for tier in _tiers(rng, buyer, settlement.settlement_date, loans_per_batch):
            batch.funded.append(_loan(rng, batch, f"L-{next_loan:06d}", tier))
            next_loan += 1
        batch.confirmation = [confirm(loan) for loan in batch.funded]
        batches.append(batch)
    return Dataset(seed, start, end, batches, board(seed, batches, end))


def board(seed: int, batches: list[Batch], end: date) -> list[ServicerOnboarding]:
    """Orlo boards each confirmed loan once, 1-3 business days after settlement."""
    rng = random.Random(f"{seed}-boarding")
    boarded: dict[str, ServicerOnboarding] = {}
    for batch in batches:
        for row in batch.confirmation or []:
            boarded_date = add_business_days(row.settlement_date, rng.randint(1, 3))
            if row.loan_id in boarded or boarded_date > end:
                continue
            boarded[row.loan_id] = ServicerOnboarding(
                loan_id=row.loan_id,
                boarded_date=boarded_date,
                upb=row.upb,
                next_payment_due_date=boarded_date + timedelta(days=30),
            )
    return sorted(boarded.values(), key=lambda o: (o.boarded_date, o.loan_id))


def _tiers(rng: random.Random, buyer: str, settlement_date: date, count: int) -> list[Tier]:
    """Every eligible tier at least once, then a weighted mix."""
    eligible = terms_in_force(buyer, settlement_date).eligible_tiers
    tiers: list[Tier] = [t for t in TIERS if t in eligible]
    weights = [w for t, w in zip(TIERS, _TIER_WEIGHTS, strict=True) if t in eligible]
    return tiers + rng.choices(tiers, weights=weights, k=count - len(tiers))


def _loan(rng: random.Random, batch: Batch, loan_id: str, tier: Tier) -> FundedLoan:
    terms = terms_in_force(batch.counterparty_id, batch.settlement_date)
    amount = Decimal(rng.randint(5_000_00, 45_000_00)).scaleb(-2)
    funding_date = add_business_days(batch.cut_off_date, -rng.randint(0, 10))
    note_rate = Decimal(rng.randint(499, 2499)).scaleb(-4)
    price_pct = terms.pricing_grid[tier]
    accrued = accrued_interest(
        amount, note_rate, funding_date, batch.settlement_date, terms.day_count
    )
    return FundedLoan.model_validate(
        {
            "loan_id": loan_id,
            "batch_id": batch.batch_id,
            "dealer_id": rng.choice(DEALERS),
            "credit_tier": tier,
            "funding_date": funding_date,
            "cut_off_date": batch.cut_off_date,
            "settlement_date": batch.settlement_date,
            "funded_amount": amount,
            "upb": amount,
            "note_rate": note_rate,
            "term_months": rng.choice(_TERMS_MONTHS),
            "price_pct": price_pct,
            "accrued_interest": accrued,
            "purchase_price": purchase_price(amount, price_pct, accrued),
        }
    )
