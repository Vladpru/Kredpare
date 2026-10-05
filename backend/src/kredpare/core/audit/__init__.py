from typing import Any

from sqlalchemy.orm import Session

from kredpare.core.tables import AuditEvent


def record_event(
    session: Session,
    actor: str,
    action: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
) -> None:
    """Add an audit event to the caller's transaction, so it commits or rolls back with it."""
    session.add(
        AuditEvent(
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            payload=payload,
        )
    )
