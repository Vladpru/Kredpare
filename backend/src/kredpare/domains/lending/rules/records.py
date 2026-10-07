"""Rules for breaks about which records exist: missing, duplicate, overdue.

Each rule explains only when the condition in docs/domain/break-taxonomy.md holds exactly.
"""

from kredpare.core.rules.types import BreakView, Explanation, RuleContext
from kredpare.domains.lending.rules._common import (
    CONFIRMATION_SCHEMA,
    FILE_OWNER,
    SELLER_SCHEMA,
)


class LoanNotConfirmed:
    """The confirmation file for the batch arrived without a loan the seller offered."""

    name = "loan_not_confirmed"
    break_types = ("missing_record",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        if brk.side_schema != CONFIRMATION_SCHEMA:
            return None
        offered = context.record(brk.left_record_id)
        if offered is None or offered.schema_name != SELLER_SCHEMA:
            return None
        # Matching only reports a missing record for a delivered batch; check it, don't trust it.
        delivered = context.find_records(
            schema_name=CONFIRMATION_SCHEMA,
            counterparty_id=brk.counterparty_id,
            batch_id=brk.batch_id,
        )
        if not delivered:
            return None
        return Explanation(
            rule=self.name,
            cause=self.name,
            wrong_side="counterparty",
            proposal="email",
            evidence={
                "loan_id": brk.record_id,
                "batch_id": brk.batch_id,
                "confirmation_rows_in_batch": len(delivered),
            },
        )


class LoanNotOffered:
    """The counterparty confirmed a loan the seller offered only in a different batch."""

    name = "loan_not_offered"
    break_types = ("missing_record",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        if brk.side_schema != SELLER_SCHEMA:
            return None
        confirmed = context.record(brk.right_record_id)
        if confirmed is None or confirmed.schema_name != CONFIRMATION_SCHEMA:
            return None
        offered = context.find_records(
            schema_name=SELLER_SCHEMA,
            counterparty_id=brk.counterparty_id,
            record_id=brk.record_id,
        )
        other_batches = sorted({r.batch_id for r in offered if r.batch_id != brk.batch_id})
        if not other_batches or any(r.batch_id == brk.batch_id for r in offered):
            return None
        return Explanation(
            rule=self.name,
            cause=self.name,
            wrong_side="counterparty",
            proposal="email",
            evidence={
                "loan_id": brk.record_id,
                "batch_id": brk.batch_id,
                "seller_batches": other_batches,
            },
        )


class DuplicateRow:
    """The same row twice in one file, identical except its row number."""

    name = "duplicate_row"
    break_types = ("duplicate",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        owner = FILE_OWNER.get(brk.side_schema or "")
        first = context.record(brk.left_record_id)
        if owner is None or first is None:
            return None
        rows = context.find_records(
            schema_name=first.schema_name,
            counterparty_id=first.counterparty_id,
            batch_id=first.batch_id,
            record_id=first.record_id,
            file_id=first.file_id,
        )
        if len(rows) < 2 or any(r.data != first.data for r in rows):
            return None
        return Explanation(
            rule=self.name,
            cause=self.name,
            wrong_side="seller" if owner == "seller" else "counterparty",
            proposal="correction" if owner == "seller" else "email",
            evidence={
                "loan_id": brk.record_id,
                "batch_id": brk.batch_id,
                "rows": len(rows),
                "row_numbers": [r.row_number for r in rows],
            },
        )


class ConfirmationOverdue:
    """No confirmation file for the batch yet, and nothing else is wrong with the loan."""

    name = "confirmation_overdue"
    break_types = ("stale_pending",)

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        if brk.side_schema != CONFIRMATION_SCHEMA:
            return None
        arrived = context.find_records(
            schema_name=CONFIRMATION_SCHEMA,
            counterparty_id=brk.counterparty_id,
            batch_id=brk.batch_id,
            limit=1,
        )
        others = [
            b
            for b in context.find_breaks(
                counterparty_id=brk.counterparty_id, record_id=brk.record_id
            )
            if b.id != brk.id
        ]
        if arrived or others:
            return None
        return Explanation(
            rule=self.name,
            cause=self.name,
            wrong_side=None,
            proposal="email",
            evidence={
                "loan_id": brk.record_id,
                "batch_id": brk.batch_id,
                "counterparty_id": brk.counterparty_id,
            },
        )
