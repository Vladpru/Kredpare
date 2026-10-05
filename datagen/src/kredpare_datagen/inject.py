"""Break injector. Every injected cause produces a real difference and one ground truth record.

Each loan carries at most one cause. Systematic causes claim their loans first (amended
prices, then hard causes, then the medium day-count change), simple causes take what is left.
Where each cause lives: docs/domain/counterparties.md, "Where each break cause lives".
"""

import copy
import random
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from kredpare.domains.lending.pricing import DayCount, Rounding, purchase_price
from kredpare.domains.lending.schemas import FundedLoan, PurchaseConfirmation

from kredpare_datagen.agreements import (
    BRACKWATER,
    QUILLMONT,
    ROUNDING_CITATION,
    TESSALINE,
    TIERS,
    Tier,
    terms_in_force,
)
from kredpare_datagen.calendar import add_business_days
from kredpare_datagen.generate import Batch, Dataset, board, quote
from kredpare_datagen.ground_truth import EXPECTED_LEVEL, Difficulty, GroundTruth, Side

STALE_AFTER_BUSINESS_DAYS = 5

# Amendments that change a computed value: (counterparty, effective date[, amended tier]).
PRICE_GRID_CHANGES: tuple[tuple[str, date, Tier], ...] = (
    (QUILLMONT, date(2026, 9, 1), "B"),
    (TESSALINE, date(2026, 8, 24), "C"),
)
DAY_COUNT_CHANGE = (BRACKWATER, date(2026, 8, 24))
UNANNOUNCED_CHANGE = (QUILLMONT, date(2026, 8, 26))

_AMOUNT_FIELDS = ("accrued_interest", "purchase_price")
_PRICE_FIELDS = ("price_pct", "purchase_price")


@dataclass(frozen=True)
class InjectionPlan:
    """How many loans each countable cause targets. Systematic causes take every eligible loan."""

    loan_not_confirmed: int = 3
    loan_not_offered: int = 2
    duplicate_row: int = 2
    settlement_date_roll: int = 3
    rounding_difference: int = 3
    accrual_start_alternative: int = 3
    accrued_interest_error: int = 4
    combined_causes: int = 3


DEFAULT_PLAN = InjectionPlan()


def inject(
    dataset: Dataset, plan: InjectionPlan = DEFAULT_PLAN
) -> tuple[Dataset, list[GroundTruth]]:
    """Return a mutated copy of the dataset and its ground truth. The input is not changed."""
    injector = _Injector(copy.deepcopy(dataset))
    injector.price_grid_amendment()
    injector.unannounced_rule_change()
    injector.dealer_wide_adjustment()
    injector.combined_causes(plan.combined_causes)
    injector.accrued_interest_error(plan.accrued_interest_error)
    injector.confirmation_overdue()
    injector.settlement_date_roll(plan.settlement_date_roll)
    injector.rounding_difference(plan.rounding_difference)
    injector.accrual_start_alternative(plan.accrual_start_alternative)
    injector.loan_not_confirmed(plan.loan_not_confirmed)
    injector.loan_not_offered(plan.loan_not_offered)
    injector.duplicate_row(plan.duplicate_row)
    result = injector.dataset
    result.onboardings = board(result.seed, result.batches, result.end)
    return result, injector.truth


def _proposal(wrong_side: Side | None) -> str:
    return "correction" if wrong_side == "seller" else "email"


class _Injector:
    def __init__(self, dataset: Dataset) -> None:
        self.dataset = dataset
        self.rng = random.Random(f"{dataset.seed}-inject")
        self.claimed: set[str] = set()
        self.truth: list[GroundTruth] = []

    # -- helpers -------------------------------------------------------------------------

    def _batches(
        self, counterparty_id: str | None = None, *, since: date | None = None
    ) -> list[Batch]:
        return [
            b
            for b in self.dataset.batches
            if b.confirmation is not None
            and (counterparty_id is None or b.counterparty_id == counterparty_id)
            and (since is None or b.settlement_date >= since)
        ]

    def _free(
        self, batch: Batch, keep: Callable[[FundedLoan], bool] = lambda _: True
    ) -> list[FundedLoan]:
        return [f for f in batch.funded if f.loan_id not in self.claimed and keep(f)]

    def _pick_loans(
        self,
        batches: Sequence[Batch],
        count: int,
        keep: Callable[[Batch, FundedLoan], bool] = lambda _b, _f: True,
    ) -> list[tuple[Batch, FundedLoan]]:
        """Up to count distinct unclaimed loans, drawn across the given batches."""
        candidates = [(b, f) for b in batches for f in self._free(b, lambda f, b=b: keep(b, f))]
        return self.rng.sample(candidates, min(count, len(candidates)))

    def _update_seller(self, batch: Batch, loan_id: str, **changes: object) -> None:
        batch.funded = [
            FundedLoan.model_validate({**f.model_dump(), **changes}) if f.loan_id == loan_id else f
            for f in batch.funded
        ]

    def _update_counterparty(self, batch: Batch, loan_id: str, **changes: object) -> None:
        assert batch.confirmation is not None
        batch.confirmation = [
            PurchaseConfirmation.model_validate({**r.model_dump(), **changes})
            if r.loan_id == loan_id
            else r
            for r in batch.confirmation
        ]

    def _record(
        self,
        cause: str,
        difficulty: Difficulty,
        batches: Sequence[Batch],
        loan_ids: Sequence[str],
        break_type: str,
        *,
        fields: tuple[str, ...] = (),
        missing_side: Side | None = None,
        wrong_side: Side | None,
        citations: tuple[str, ...] = (),
    ) -> None:
        self.claimed.update(loan_ids)
        self.truth.append(
            GroundTruth.model_validate(
                {
                    "break_id": f"gt-{len(self.truth) + 1:06d}",
                    "counterparty_id": batches[0].counterparty_id,
                    "batch_ids": tuple(b.batch_id for b in batches),
                    "loan_ids": tuple(loan_ids),
                    "break_type": break_type,
                    "fields": fields,
                    "missing_side": missing_side,
                    "cause": cause,
                    "difficulty": difficulty,
                    "wrong_side": wrong_side,
                    "expected_level": EXPECTED_LEVEL[difficulty],
                    "expected_citations": citations,
                    "expected_proposal": _proposal(wrong_side),
                }
            )
        )

    def _side(self) -> Side:
        return self.rng.choice(("seller", "counterparty"))

    def _apply(
        self, batch: Batch, loan: FundedLoan, side: Side, accrued: Decimal, price_pct: Decimal
    ) -> None:
        """Make one side compute this loan differently; the seller file stays consistent."""
        changes = {
            "price_pct": price_pct,
            "accrued_interest": accrued,
            "purchase_price": purchase_price(loan.upb, price_pct, accrued),
        }
        if side == "seller":
            self._update_seller(batch, loan.loan_id, **changes)
        else:
            self._update_counterparty(batch, loan.loan_id, **changes)

    # -- medium and hard: systematic causes ----------------------------------------------

    def price_grid_amendment(self) -> None:
        """One side keeps the pre-amendment price for every amended-tier loan of a batch."""
        for counterparty_id, effective, tier in PRICE_GRID_CHANGES:
            old_price = terms_in_force(counterparty_id, effective - timedelta(days=1)).pricing_grid[
                tier
            ]
            for batch in self._batches(counterparty_id, since=effective):
                terms = terms_in_force(counterparty_id, batch.settlement_date)
                side = self._side()
                for loan in self._free(batch, lambda f, tier=tier: f.credit_tier == tier):
                    self._apply(batch, loan, side, loan.accrued_interest, old_price)
                    self._record(
                        "price_grid_amendment",
                        "medium",
                        [batch],
                        [loan.loan_id],
                        "amount_mismatch",
                        fields=_PRICE_FIELDS,
                        wrong_side=side,
                        citations=(terms.pricing_citation,),
                    )

    def unannounced_rule_change(self) -> None:
        """From one batch on, the buyer counts the settlement day too. No amendment says so."""
        counterparty_id, since = UNANNOUNCED_CHANGE
        batches = self._batches(counterparty_id, since=since)
        loan_ids: list[str] = []
        for batch in batches:
            terms = terms_in_force(counterparty_id, batch.settlement_date)
            for loan in self._free(batch):
                accrued, _ = quote(
                    loan, price_pct=loan.price_pct, day_count=terms.day_count, end_inclusive=True
                )
                self._apply(batch, loan, "counterparty", accrued, loan.price_pct)
                loan_ids.append(loan.loan_id)
        if loan_ids:
            terms = terms_in_force(counterparty_id, since)
            self._record(
                "unannounced_rule_change",
                "hard",
                batches,
                loan_ids,
                "amount_mismatch",
                fields=_AMOUNT_FIELDS,
                wrong_side="counterparty",
                citations=(terms.accrual_citation,),
            )

    def dealer_wide_adjustment(self) -> None:
        """Every loan of one dealer in one batch is priced one tier lower by the buyer."""
        candidates: list[tuple[Batch, str]] = []
        for batch in self._batches(TESSALINE):
            if batch.settlement_date >= PRICE_GRID_CHANGES[1][1]:
                continue  # keep the pricing grid unambiguous
            for dealer in sorted({f.dealer_id for f in batch.funded}):
                loans = [f for f in batch.funded if f.dealer_id == dealer]
                if (
                    len(loans) >= 2
                    and all(f.loan_id not in self.claimed for f in loans)
                    and all(f.credit_tier != TIERS[-1] for f in loans)  # D has no lower tier
                ):
                    candidates.append((batch, dealer))
        if not candidates:
            return
        batch, dealer = self.rng.choice(candidates)
        terms = terms_in_force(TESSALINE, batch.settlement_date)
        loans = [f for f in batch.funded if f.dealer_id == dealer]
        for loan in loans:
            lower = TIERS[TIERS.index(loan.credit_tier) + 1]
            self._apply(
                batch, loan, "counterparty", loan.accrued_interest, terms.pricing_grid[lower]
            )
        self._record(
            "dealer_wide_adjustment",
            "hard",
            [batch],
            [f.loan_id for f in loans],
            "amount_mismatch",
            fields=_PRICE_FIELDS,
            wrong_side="counterparty",
            citations=(terms.pricing_citation,),
        )

    def _day_count_batches(self) -> tuple[list[Batch], DayCount]:
        counterparty_id, effective = DAY_COUNT_CHANGE
        old = terms_in_force(counterparty_id, effective - timedelta(days=1)).day_count
        return self._batches(counterparty_id, since=effective), old

    def combined_causes(self, count: int) -> None:
        """Pre-amendment day count and truncation on the same loans."""
        batches, old = self._day_count_batches()
        if not batches:
            return
        batch = self.rng.choice(batches)
        terms = terms_in_force(batch.counterparty_id, batch.settlement_date)

        def combined(f: FundedLoan) -> Decimal:
            accrued, _ = quote(f, price_pct=f.price_pct, day_count=old, rounding=Rounding.TRUNCATE)
            return accrued

        def leaves_residual(_b: Batch, f: FundedLoan) -> bool:
            singles = {
                f.accrued_interest,
                quote(f, price_pct=f.price_pct, day_count=old)[0],
                quote(
                    f, price_pct=f.price_pct, day_count=terms.day_count, rounding=Rounding.TRUNCATE
                )[0],
            }
            return combined(f) not in singles

        picked = self._pick_loans([batch], count, leaves_residual)
        if len(picked) < 2:
            return
        picked.sort(key=lambda pair: pair[1].loan_id)
        for _, loan in picked:
            self._apply(batch, loan, "counterparty", combined(loan), loan.price_pct)
        self._record(
            "combined_causes",
            "hard",
            [batch],
            [loan.loan_id for _, loan in picked],
            "amount_mismatch",
            fields=_AMOUNT_FIELDS,
            wrong_side="counterparty",
            citations=(terms.accrual_citation, ROUNDING_CITATION),
        )

    def accrued_interest_error(self, count: int) -> None:
        """One side keeps the pre-amendment day count."""
        batches, old = self._day_count_batches()
        for batch in batches:
            terms = terms_in_force(batch.counterparty_id, batch.settlement_date)
            side = self._side()

            def differs(_b: Batch, f: FundedLoan) -> bool:
                return quote(f, price_pct=f.price_pct, day_count=old)[0] != f.accrued_interest

            for _, loan in sorted(
                self._pick_loans([batch], count, differs), key=lambda p: p[1].loan_id
            ):
                accrued, _ = quote(loan, price_pct=loan.price_pct, day_count=old)
                self._apply(batch, loan, side, accrued, loan.price_pct)
                self._record(
                    "accrued_interest_error",
                    "medium",
                    [batch],
                    [loan.loan_id],
                    "amount_mismatch",
                    fields=_AMOUNT_FIELDS,
                    wrong_side=side,
                    citations=(terms.accrual_citation,),
                )

    # -- simple --------------------------------------------------------------------------

    def confirmation_overdue(self) -> None:
        """A whole confirmation file not received, past the stale threshold at window end."""
        candidates = [
            b
            for b in self._batches()
            if add_business_days(b.cut_off_date, STALE_AFTER_BUSINESS_DAYS) < self.dataset.end
            and len(self._free(b)) == len(b.funded)
        ]
        if not candidates:
            return
        batch = self.rng.choice(candidates)
        batch.confirmation = None
        for loan in batch.funded:
            self._record(
                "confirmation_overdue",
                "simple",
                [batch],
                [loan.loan_id],
                "stale_pending",
                wrong_side=None,
            )

    def settlement_date_roll(self, count: int) -> None:
        """The buyer keeps the scheduled date instead of rolling it to a business day."""
        rolled = [b for b in self._batches() if b.settlement.scheduled_date != b.settlement_date]
        for batch, loan in self._sorted(self._pick_loans(rolled, count)):
            self._update_counterparty(
                batch, loan.loan_id, settlement_date=batch.settlement.scheduled_date
            )
            self._record(
                "settlement_date_roll",
                "simple",
                [batch],
                [loan.loan_id],
                "date_mismatch",
                fields=("settlement_date",),
                wrong_side="counterparty",
            )

    def rounding_difference(self, count: int) -> None:
        """Brackwater's cents-as-int system truncates accrued interest."""

        def truncated(b: Batch, f: FundedLoan) -> Decimal:
            terms = terms_in_force(b.counterparty_id, b.settlement_date)
            return quote(
                f, price_pct=f.price_pct, day_count=terms.day_count, rounding=Rounding.TRUNCATE
            )[0]

        picked = self._pick_loans(
            self._batches(BRACKWATER), count, lambda b, f: truncated(b, f) != f.accrued_interest
        )
        for batch, loan in self._sorted(picked):
            self._apply(batch, loan, "counterparty", truncated(batch, loan), loan.price_pct)
            self._record(
                "rounding_difference",
                "simple",
                [batch],
                [loan.loan_id],
                "amount_mismatch",
                fields=_AMOUNT_FIELDS,
                wrong_side="counterparty",
            )

    def accrual_start_alternative(self, count: int) -> None:
        """Tessaline accrues from the cut-off date instead of the funding date."""

        def from_cut_off(b: Batch, f: FundedLoan) -> Decimal:
            terms = terms_in_force(b.counterparty_id, b.settlement_date)
            return quote(
                f, price_pct=f.price_pct, day_count=terms.day_count, accrual_start=f.cut_off_date
            )[0]

        picked = self._pick_loans(
            self._batches(TESSALINE), count, lambda b, f: from_cut_off(b, f) != f.accrued_interest
        )
        for batch, loan in self._sorted(picked):
            self._apply(batch, loan, "counterparty", from_cut_off(batch, loan), loan.price_pct)
            self._record(
                "accrual_start_alternative",
                "simple",
                [batch],
                [loan.loan_id],
                "amount_mismatch",
                fields=_AMOUNT_FIELDS,
                wrong_side="counterparty",
            )

    def loan_not_confirmed(self, count: int) -> None:
        for batch, loan in self._sorted(self._pick_loans(self._batches(), count)):
            assert batch.confirmation is not None
            batch.confirmation = [r for r in batch.confirmation if r.loan_id != loan.loan_id]
            self._record(
                "loan_not_confirmed",
                "simple",
                [batch],
                [loan.loan_id],
                "missing_record",
                missing_side="counterparty",
                wrong_side="counterparty",
            )

    def loan_not_offered(self, count: int) -> None:
        """The buyer confirms, in one batch, a loan the seller offered in another batch."""
        for _ in range(count):
            targets = [
                (target, source)
                for target in self._batches()
                for source in self.dataset.batches
                if source.counterparty_id == target.counterparty_id
                and source is not target
                and self._free(source)
            ]
            if not targets:
                return
            target, source = self.rng.choice(targets)
            loan = self.rng.choice(self._free(source))
            assert target.confirmation is not None
            target.confirmation.append(
                PurchaseConfirmation.model_validate(
                    {
                        "loan_id": loan.loan_id,
                        "batch_id": target.batch_id,
                        "settlement_date": target.settlement_date,
                        "upb": loan.upb,
                        "price_pct": loan.price_pct,
                        "accrued_interest": loan.accrued_interest,
                        "purchase_price": loan.purchase_price,
                    }
                )
            )
            self._record(
                "loan_not_offered",
                "simple",
                [target],
                [loan.loan_id],
                "missing_record",
                missing_side="seller",
                wrong_side="counterparty",
            )

    def duplicate_row(self, count: int) -> None:
        """The same row twice in one file; the file owner is wrong."""
        for batch, loan in self._sorted(self._pick_loans(self._batches(), count)):
            side = self._side()
            if side == "seller":
                index = batch.funded.index(loan)
                batch.funded.insert(index + 1, loan)
            else:
                assert batch.confirmation is not None
                index = next(
                    i for i, r in enumerate(batch.confirmation) if r.loan_id == loan.loan_id
                )
                batch.confirmation.insert(index + 1, batch.confirmation[index])
            self._record(
                "duplicate_row", "simple", [batch], [loan.loan_id], "duplicate", wrong_side=side
            )

    @staticmethod
    def _sorted(picked: list[tuple[Batch, FundedLoan]]) -> list[tuple[Batch, FundedLoan]]:
        return sorted(picked, key=lambda pair: pair[1].loan_id)
