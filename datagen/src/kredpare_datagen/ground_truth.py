"""One labeled record per injected cause instance. Format: docs/domain/break-taxonomy.md."""

from typing import Literal

from pydantic import BaseModel, ConfigDict

Side = Literal["seller", "counterparty"]
Difficulty = Literal["simple", "medium", "hard"]

EXPECTED_LEVEL = {"simple": "rule", "medium": "workflow", "hard": "agent"}


class GroundTruth(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    break_id: str
    counterparty_id: str
    batch_ids: tuple[str, ...]
    loan_ids: tuple[str, ...]
    break_type: Literal[
        "missing_record", "duplicate", "amount_mismatch", "date_mismatch", "stale_pending"
    ]
    fields: tuple[str, ...]
    """Compared fields that differ; empty for missing, duplicate, and stale records."""
    missing_side: Side | None
    cause: str
    difficulty: Difficulty
    wrong_side: Side | None
    """None when nobody is wrong yet (a reminder)."""
    expected_level: Literal["rule", "workflow", "agent"]
    expected_citations: tuple[str, ...]
    expected_proposal: Literal["email", "correction"]
