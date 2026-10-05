"""What a rule sees and returns. Core vocabulary only; a domain's rules live in the domain."""

import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal, Protocol

WrongSide = Literal["seller", "counterparty"]
ProposalKind = Literal["correction", "email"]

JsonValue = str | int | bool | None | Sequence["JsonValue"] | Mapping[str, "JsonValue"]
"""Evidence is stored as JSONB: amounts and rates are exact decimal strings, dates ISO strings."""


@dataclass(frozen=True)
class RecordView:
    """A stored record as a rule sees it. Values are canonical, in JSON form."""

    id: uuid.UUID
    file_id: uuid.UUID
    row_number: int
    counterparty_id: str
    batch_id: str
    record_id: str
    schema_name: str
    data: Mapping[str, object]


@dataclass(frozen=True)
class BreakView:
    """A stored break as a rule sees it. Read-only."""

    id: uuid.UUID
    as_of: date
    break_type: str
    left_schema: str
    right_schema: str | None
    side_schema: str | None
    counterparty_id: str
    batch_id: str
    record_id: str
    field: str | None
    left_record_id: uuid.UUID | None
    right_record_id: uuid.UUID | None
    left_value: str | None
    right_value: str | None
    delta: Decimal | None


@dataclass(frozen=True)
class Explanation:
    """Why a break exists, as one rule recomputed or observed it. Not applied without approval."""

    rule: str
    cause: str
    wrong_side: WrongSide | None
    """None when nobody is wrong yet (a reminder)."""
    proposal: ProposalKind
    evidence: Mapping[str, JsonValue] = field(default_factory=dict[str, JsonValue])


class RuleContext(Protocol):
    """Read-only, parameterized access to what a rule may look at. No free SQL."""

    def record(self, record_pk: uuid.UUID | None) -> RecordView | None: ...

    def find_records(
        self,
        *,
        schema_name: str | None = None,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        record_id: str | None = None,
        file_id: uuid.UUID | None = None,
        limit: int | None = None,
    ) -> tuple[RecordView, ...]:
        """Records matching every given filter, ordered by file and row number."""
        ...

    def find_breaks(
        self,
        *,
        counterparty_id: str | None = None,
        batch_id: str | None = None,
        record_id: str | None = None,
    ) -> tuple[BreakView, ...]:
        """Breaks of any status matching every given filter."""
        ...
