"""Settlement date roll: one side moved a non-business settlement date to the next business day."""

from datetime import date

from kredpare.core.rules.types import BreakView, Explanation, RuleContext
from kredpare.domains.lending.calendar import following_business_day, is_business_day


class SettlementDateRoll:
    name = "settlement_date_roll"
    break_types = ("date_mismatch",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        if brk.field != "settlement_date" or brk.left_value is None or brk.right_value is None:
            return None
        seller, counterparty = (
            date.fromisoformat(brk.left_value),
            date.fromisoformat(brk.right_value),
        )
        if _is_roll(scheduled=counterparty, rolled=seller):
            scheduled, rolled, rolled_by = counterparty, seller, "seller"
        elif _is_roll(scheduled=seller, rolled=counterparty):
            scheduled, rolled, rolled_by = seller, counterparty, "counterparty"
        else:
            return None
        # The side that did not roll is the one that differs from the business-day calendar.
        wrong_side = "counterparty" if rolled_by == "seller" else "seller"
        return Explanation(
            rule=self.name,
            cause=self.name,
            wrong_side=wrong_side,
            proposal="email" if wrong_side == "counterparty" else "correction",
            evidence={
                "field": "settlement_date",
                "seller_value": brk.left_value,
                "counterparty_value": brk.right_value,
                "scheduled_date": scheduled.isoformat(),
                "rolled_date": rolled.isoformat(),
                "side_that_rolled": rolled_by,
            },
        )


def _is_roll(*, scheduled: date, rolled: date) -> bool:
    """rolled is exactly the following business day of a scheduled date that is not one."""
    return not is_business_day(scheduled) and following_business_day(scheduled) == rolled
