"""Break detection eval: matching output against kredpare-datagen ground truth.

Ground truth labels causes; matching emits one break per (record, field). Both sides are
reduced to comparable keys:
- amount_mismatch, date_mismatch: (type, loan_id, field)
- missing_record, duplicate, stale_pending: (type, batch_id, loan_id, side)
"""

import json
from collections.abc import Iterable
from dataclasses import dataclass

from kredpare.core.matching import DetectedBreak

BREAK_TYPES = ("missing_record", "duplicate", "amount_mismatch", "date_mismatch", "stale_pending")
_SIDES = {
    "FundedLoan": "seller",
    "PurchaseConfirmation": "counterparty",
    "ServicerOnboarding": "servicer",
}

Key = tuple[str, ...]


def expected_keys(ground_truth_lines: Iterable[str]) -> set[Key]:
    keys: set[Key] = set()
    for line in ground_truth_lines:
        if not line.strip():
            continue
        record = json.loads(line)
        kind: str = record["break_type"]
        batch_id: str = record["batch_ids"][0]
        for loan_id in record["loan_ids"]:
            if kind in ("amount_mismatch", "date_mismatch"):
                keys.update((kind, loan_id, field) for field in record["fields"])
            elif kind == "missing_record":
                keys.add((kind, batch_id, loan_id, record["missing_side"]))
            elif kind == "duplicate":
                keys.add((kind, batch_id, loan_id, record["wrong_side"]))
            else:  # stale_pending: the confirmation has not arrived
                keys.add((kind, batch_id, loan_id, "counterparty"))
    return keys


def actual_keys(breaks: Iterable[DetectedBreak]) -> set[Key]:
    keys: set[Key] = set()
    for found in breaks:
        if found.break_type in ("amount_mismatch", "date_mismatch"):
            keys.add((found.break_type, found.record_id, found.field or ""))
        else:
            side = _SIDES.get(found.side_schema or "", found.side_schema or "")
            keys.add((found.break_type, found.batch_id, found.record_id, side))
    return keys


@dataclass(frozen=True)
class TypeScore:
    precision: float
    recall: float
    support: int
    false_positives: tuple[Key, ...]
    false_negatives: tuple[Key, ...]


def score(expected: set[Key], actual: set[Key]) -> dict[str, TypeScore]:
    result: dict[str, TypeScore] = {}
    for kind in BREAK_TYPES:
        want = {k for k in expected if k[0] == kind}
        got = {k for k in actual if k[0] == kind}
        hits = len(want & got)
        result[kind] = TypeScore(
            precision=hits / len(got) if got else 1.0,
            recall=hits / len(want) if want else 1.0,
            support=len(want),
            false_positives=tuple(sorted(got - want)),
            false_negatives=tuple(sorted(want - got)),
        )
    return result
