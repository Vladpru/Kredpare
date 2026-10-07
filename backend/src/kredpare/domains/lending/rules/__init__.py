"""Pure recompute rules for simple lending causes.

A rule explains a mismatch only when recomputation reproduces the counterparty value exactly.
No tolerance is ever used to explain; anything else returns None (not_explained).
"""

from kredpare.domains.lending.rules._recompute import (
    RecomputeEvidence,
    accrual_start_alternative,
    rounding_difference,
)

__all__ = ["RecomputeEvidence", "accrual_start_alternative", "rounding_difference"]
