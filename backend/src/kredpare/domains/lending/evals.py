"""Break detection eval: matching output against kredpare-datagen ground truth.

Ground truth labels causes; matching emits one break per (record, field). Both sides are
reduced to comparable keys:
- amount_mismatch, date_mismatch: (type, loan_id, field)
- missing_record, duplicate, stale_pending: (type, batch_id, loan_id, side)
"""

import json
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass

from kredpare.core.matching import DetectedBreak

BREAK_TYPES = ("missing_record", "duplicate", "amount_mismatch", "date_mismatch", "stale_pending")
_SIDES = {
    "FundedLoan": "seller",
    "PurchaseConfirmation": "counterparty",
    "ServicerOnboarding": "servicer",
}

Key = tuple[str, ...]


def _expand(record: Mapping[str, object]) -> list[Key]:
    """One key per (loan, field) for compared fields, one per loan otherwise."""
    kind = str(record["break_type"])
    loan_ids: list[str] = list(record["loan_ids"])  # type: ignore[call-overload]
    batch_id = str(record["batch_ids"][0])  # type: ignore[index]
    fields: list[str] = list(record["fields"])  # type: ignore[call-overload]
    keys: list[Key] = []
    for loan_id in loan_ids:
        if kind in ("amount_mismatch", "date_mismatch"):
            keys += [(kind, loan_id, field) for field in fields]
        elif kind == "missing_record":
            keys.append((kind, batch_id, loan_id, str(record["missing_side"])))
        elif kind == "duplicate":
            keys.append((kind, batch_id, loan_id, str(record["wrong_side"])))
        else:  # stale_pending: the confirmation has not arrived
            keys.append((kind, batch_id, loan_id, "counterparty"))
    return keys


def _records(ground_truth_lines: Iterable[str]) -> Iterable[Mapping[str, object]]:
    return (json.loads(line) for line in ground_truth_lines if line.strip())


def expected_keys(ground_truth_lines: Iterable[str]) -> set[Key]:
    return {key for record in _records(ground_truth_lines) for key in _expand(record)}


def break_key(found: DetectedBreak) -> Key:
    if found.break_type in ("amount_mismatch", "date_mismatch"):
        return (found.break_type, found.record_id, found.field or "")
    side = _SIDES.get(found.side_schema or "", found.side_schema or "")
    return (found.break_type, found.batch_id, found.record_id, side)


def actual_keys(breaks: Iterable[DetectedBreak]) -> set[Key]:
    return {break_key(found) for found in breaks}


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


@dataclass(frozen=True)
class Label:
    """What ground truth says about one expanded break."""

    cause: str
    difficulty: str
    wrong_side: str | None
    proposal: str


@dataclass(frozen=True)
class Verdict:
    """What the rule level said about one break."""

    cause: str
    wrong_side: str | None
    proposal: str


def expected_labels(ground_truth_lines: Iterable[str]) -> dict[Key, Label]:
    """Ground truth expanded like expected_keys, keeping the cause and the expected outcome."""
    labels: dict[Key, Label] = {}
    for record in _records(ground_truth_lines):
        side = record["wrong_side"]
        label = Label(
            cause=str(record["cause"]),
            difficulty=str(record["difficulty"]),
            wrong_side=None if side is None else str(side),
            proposal=str(record["expected_proposal"]),
        )
        labels.update((key, label) for key in _expand(record))
    return labels


@dataclass(frozen=True)
class RuleTally:
    support: int = 0
    explained: int = 0
    cause_correct: int = 0
    wrong_side_correct: int = 0
    proposal_correct: int = 0

    @property
    def explained_share(self) -> float:
        return self.explained / self.support if self.support else 1.0

    @property
    def cause_accuracy(self) -> float:
        return self.cause_correct / self.explained if self.explained else 1.0

    @property
    def wrong_side_accuracy(self) -> float:
        return self.wrong_side_correct / self.explained if self.explained else 1.0

    @property
    def proposal_accuracy(self) -> float:
        return self.proposal_correct / self.explained if self.explained else 1.0


@dataclass(frozen=True)
class RulesScore:
    by_difficulty: dict[str, RuleTally]
    by_cause: dict[str, RuleTally]
    cause_difficulty: dict[str, str]
    false_claims: tuple[Key, ...]
    """Medium and hard breaks a rule explained."""
    unlabeled_explained: tuple[Key, ...]
    """Explained breaks that ground truth does not know."""

    @property
    def s2(self) -> float:
        """Share of simple breaks explained by rules."""
        return self.by_difficulty.get("simple", RuleTally()).explained_share

    @property
    def s3(self) -> int:
        """Medium and hard breaks explained by any rule."""
        return len(self.false_claims)


def _add(tally: RuleTally, label: Label, verdict: Verdict | None) -> RuleTally:
    if verdict is None:
        return RuleTally(tally.support + 1, tally.explained, *_rest(tally))
    return RuleTally(
        tally.support + 1,
        tally.explained + 1,
        tally.cause_correct + (verdict.cause == label.cause),
        tally.wrong_side_correct + (verdict.wrong_side == label.wrong_side),
        tally.proposal_correct + (verdict.proposal == label.proposal),
    )


def _rest(tally: RuleTally) -> tuple[int, int, int]:
    return tally.cause_correct, tally.wrong_side_correct, tally.proposal_correct


def score_rules(labels: Mapping[Key, Label], verdicts: Mapping[Key, Verdict]) -> RulesScore:
    by_difficulty: dict[str, RuleTally] = defaultdict(RuleTally)
    by_cause: dict[str, RuleTally] = defaultdict(RuleTally)
    cause_difficulty: dict[str, str] = {}
    false_claims: list[Key] = []
    for key, label in labels.items():
        verdict = verdicts.get(key)
        by_difficulty[label.difficulty] = _add(by_difficulty[label.difficulty], label, verdict)
        by_cause[label.cause] = _add(by_cause[label.cause], label, verdict)
        cause_difficulty[label.cause] = label.difficulty
        if verdict is not None and label.difficulty != "simple":
            false_claims.append(key)
    return RulesScore(
        dict(by_difficulty),
        dict(by_cause),
        cause_difficulty,
        tuple(sorted(false_claims)),
        tuple(sorted(k for k in verdicts if k not in labels)),
    )
