from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from kredpare.core.domain import DomainSpec
from kredpare.core.ingest import ingest_directory
from kredpare.core.matching.store import run_matching
from kredpare.core.rules.runner import run_rules
from kredpare.core.rules.types import BreakView, Explanation, RuleContext
from kredpare.core.tables import AuditEvent, Break, ExplanationRow
from kredpare.domains.lending.spec import LENDING
from tests.test_core_ingest import SELLER, _write

AS_OF = date(2026, 9, 4)
OFF_BY_A_CENT = (
    "Loan Number,Settle Date,Principal Balance,Purchase Price %,Accrued Int,Total Price\n"
    'L-004512,09/02/2026,"$20,300.00",101.500,$72.22,"$20,676.73"\n'
)


@dataclass(frozen=True)
class FakeRule:
    name: str
    break_types: tuple[str, ...]
    explains: bool = True
    cause: str = "fake_cause"
    seen_context: list[RuleContext] | None = None

    def explain(self, brk: BreakView, context: RuleContext) -> Explanation | None:
        if self.seen_context is not None:
            self.seen_context.append(context)
        if not self.explains:
            return None
        return Explanation(
            rule=self.name,
            cause=self.cause,
            wrong_side="counterparty",
            proposal="email",
            evidence={"delta": str(brk.delta)},
        )


def _with_breaks(engine: Engine, tmp_path: Path) -> None:
    _write(
        tmp_path,
        {
            "seller/a.csv": (SELLER, "FundedLoan", "cp-quillmont"),
            "cp-quillmont/a.csv": (OFF_BY_A_CENT, "PurchaseConfirmation", "cp-quillmont"),
        },
    )
    ingest_directory(engine, LENDING, tmp_path)
    run_matching(engine, LENDING, AS_OF)


def _spec(*rules: FakeRule) -> DomainSpec:
    return replace(LENDING, rules=rules)


def _only_break(engine: Engine) -> Break:
    with Session(engine) as session:
        return session.scalars(select(Break)).one()


def test_one_explaining_rule_explains_the_break(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)

    report = run_rules(engine, _spec(FakeRule("r1", ("amount_mismatch",))))

    assert (report.explained, report.pending_workflow) == (1, 0)
    assert report.by_rule == {"r1": 1}
    with Session(engine) as session:
        brk = session.scalars(select(Break)).one()
        explanation = session.scalars(select(ExplanationRow)).one()
        assert brk.status == "explained"
        assert (explanation.break_id, explanation.level) == (brk.id, "rule")
        assert (explanation.rule, explanation.cause) == ("r1", "fake_cause")
        assert (explanation.wrong_side, explanation.proposal) == ("counterparty", "email")
        assert explanation.evidence == {"delta": "-0.010000"}


def test_no_rule_for_the_break_type_sends_it_to_the_workflow(
    engine: Engine, tmp_path: Path
) -> None:
    _with_breaks(engine, tmp_path)

    report = run_rules(engine, _spec(FakeRule("r1", ("duplicate",))))

    assert (report.explained, report.pending_workflow) == (0, 1)
    assert _only_break(engine).status == "pending_workflow"
    with Session(engine) as session:
        assert session.scalars(select(ExplanationRow)).all() == []


def test_rules_that_do_not_explain_send_it_to_the_workflow(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)

    run_rules(engine, _spec(FakeRule("r1", ("amount_mismatch",), explains=False)))

    assert _only_break(engine).status == "pending_workflow"


def test_two_explaining_rules_conflict_and_nothing_is_stored(
    engine: Engine, tmp_path: Path
) -> None:
    _with_breaks(engine, tmp_path)

    report = run_rules(
        engine,
        _spec(FakeRule("r1", ("amount_mismatch",)), FakeRule("r2", ("amount_mismatch",))),
    )

    assert (report.explained, report.pending_workflow, report.conflicts) == (0, 1, 1)
    assert _only_break(engine).status == "pending_workflow"
    with Session(engine) as session:
        assert session.scalars(select(ExplanationRow)).all() == []
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "break_status_changed")
        ).one()
        assert event.payload["conflicting_rules"] == ["r1", "r2"]


def test_only_rules_that_handle_the_break_type_are_asked(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)
    asked: list[RuleContext] = []

    run_rules(
        engine,
        _spec(
            FakeRule("other", ("duplicate",), seen_context=asked),
            FakeRule("r1", ("amount_mismatch",)),
        ),
    )

    assert asked == []
    assert _only_break(engine).status == "explained"


def test_rerun_changes_nothing(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)
    spec = _spec(FakeRule("r1", ("amount_mismatch",)))
    run_rules(engine, spec)
    with Session(engine) as session:
        events = len(session.scalars(select(AuditEvent)).all())

    report = run_rules(engine, spec)

    assert (report.explained, report.pending_workflow) == (0, 0)
    with Session(engine) as session:
        assert len(session.scalars(select(ExplanationRow)).all()) == 1
        assert len(session.scalars(select(AuditEvent)).all()) == events


def test_status_change_is_audited(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)

    run_rules(engine, _spec(FakeRule("r1", ("amount_mismatch",))))

    with Session(engine) as session:
        brk = session.scalars(select(Break)).one()
        explanation = session.scalars(select(ExplanationRow)).one()
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "break_status_changed")
        ).one()
        assert event.actor == "rule:r1"
        assert (event.entity_type, event.entity_id) == ("break", str(brk.id))
        assert event.payload == {
            "old_status": "open",
            "new_status": "explained",
            "explanation_id": str(explanation.id),
            "rule": "r1",
            "cause": "fake_cause",
        }


def test_pending_workflow_is_audited_with_the_cascade_actor(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)

    run_rules(engine, _spec())

    with Session(engine) as session:
        event = session.scalars(
            select(AuditEvent).where(AuditEvent.action == "break_status_changed")
        ).one()
        assert event.actor == "cascade"
        assert event.payload == {"old_status": "open", "new_status": "pending_workflow"}


def test_the_context_reads_records_and_breaks(engine: Engine, tmp_path: Path) -> None:
    _with_breaks(engine, tmp_path)
    seen: list[RuleContext] = []
    run_rules(engine, _spec(FakeRule("r1", ("amount_mismatch",), seen_context=seen)))
    context = seen[0]
    brk = _only_break(engine)

    left = context.record(brk.left_record_id)
    assert left is not None
    assert (left.schema_name, left.record_id, left.data["accrued_interest"]) == (
        "FundedLoan",
        "L-004512",
        "72.23",
    )
    found = context.find_records(schema_name="PurchaseConfirmation", record_id="L-004512")
    assert [r.schema_name for r in found] == ["PurchaseConfirmation"]
    assert context.find_records(batch_id="nope") == ()
    assert [b.id for b in context.find_breaks(record_id="L-004512")] == [brk.id]
    assert context.record(None) is None
