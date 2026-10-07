"""Lending rules, one per simple cause in docs/domain/break-taxonomy.md.

A rule explains a break only when its condition holds exactly; recompute rules reproduce the
counterparty value to the cent or stay silent. No tolerance is ever used to explain.
Pure recompute rules for simple lending causes.

A rule explains a mismatch only when recomputation reproduces the counterparty value exactly.
No tolerance is ever used to explain; anything else returns None (not_explained).
"""

from kredpare.domains.lending.rules._recompute import (
    RecomputeEvidence,
    accrual_start_alternative,
    rounding_difference,
)
from kredpare.domains.lending.rules.amounts import AccrualStartAlternative, RoundingDifference
from kredpare.domains.lending.rules.records import (
    ConfirmationOverdue,
    DuplicateRow,
    LoanNotConfirmed,
    LoanNotOffered,
)
from kredpare.domains.lending.rules.settlement import SettlementDateRoll

RULES = (
    LoanNotConfirmed(),
    LoanNotOffered(),
    DuplicateRow(),
    ConfirmationOverdue(),
    SettlementDateRoll(),
    RoundingDifference(),
    AccrualStartAlternative(),
)

__all__ = ["RULES", "RecomputeEvidence", "accrual_start_alternative", "rounding_difference"]
