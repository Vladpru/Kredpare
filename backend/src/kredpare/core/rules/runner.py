"""Rule level of the cascade: explain open breaks, hand the rest to the workflow.

A break is explained only when exactly one rule explains it. Zero explaining rules, or more
than one, leaves the break to the workflow with no explanation stored: picking one of two
rules would be a guess, and a wrong rule explanation is worse than a workflow call.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.core.audit import record_event
from kredpare.core.domain import DomainSpec
from kredpare.core.rules.context import SessionRuleContext, break_view
from kredpare.core.rules.types import Explanation
from kredpare.core.tables import Break, ExplanationRow

OPEN = "open"
EXPLAINED = "explained"
PENDING_WORKFLOW = "pending_workflow"


@dataclass(frozen=True)
class RuleReport:
    explained: int = 0
    pending_workflow: int = 0
    conflicts: int = 0
    """Breaks explained by more than one rule; counted in pending_workflow too."""
    by_rule: dict[str, int] = field(default_factory=dict[str, int])
    """Explained breaks per rule."""


def run_rules(engine: Engine, spec: DomainSpec, *, actor: str = "cascade") -> RuleReport:
    """Run the rules of the domain over every open break. Rerunning finds nothing left to do."""
    explained = pending = conflicts = 0
    by_rule: Counter[str] = Counter()
    with Session(engine) as session:
        context = SessionRuleContext(session)
        for row in session.scalars(select(Break).where(Break.status == OPEN).order_by(Break.key)):
            view = break_view(row)
            claims: list[Explanation] = []
            for rule in spec.rules:
                if view.break_type not in rule.break_types:
                    continue
                found = rule.explain(view, context)
                if found is not None:
                    claims.append(found)

            if len(claims) == 1:
                claim = claims[0]
                stored = ExplanationRow(
                    id=uuid.uuid4(),
                    break_id=row.id,
                    level="rule",
                    rule=claim.rule,
                    cause=claim.cause,
                    wrong_side=claim.wrong_side,
                    proposal=claim.proposal,
                    evidence=dict(claim.evidence),
                )
                session.add(stored)
                session.flush()
                row.status = EXPLAINED
                record_event(
                    session,
                    f"rule:{claim.rule}",
                    "break_status_changed",
                    "break",
                    str(row.id),
                    {
                        "old_status": OPEN,
                        "new_status": EXPLAINED,
                        "explanation_id": str(stored.id),
                        "rule": claim.rule,
                        "cause": claim.cause,
                    },
                )
                explained += 1
                by_rule[claim.rule] += 1
                continue

            payload: dict[str, object] = {"old_status": OPEN, "new_status": PENDING_WORKFLOW}
            if claims:
                payload["conflicting_rules"] = sorted(c.rule for c in claims)
                conflicts += 1
            row.status = PENDING_WORKFLOW
            record_event(session, actor, "break_status_changed", "break", str(row.id), payload)
            pending += 1
        session.commit()
    return RuleReport(explained, pending, conflicts, dict(by_rule))
