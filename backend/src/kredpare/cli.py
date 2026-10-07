"""kredpare: ingest files, run matching, the rule and workflow levels, and measure them.

The composition root: the only place that picks a domain (lending) and hands it to core.
"""

import argparse
import sys
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, RowMapping, create_engine, make_url, select, text

from kredpare.core.cases.llm import LLMClient
from kredpare.core.cases.openai_compatible import OpenAICompatibleClient
from kredpare.core.cases.runner import WorkflowReport, run_workflow_level
from kredpare.core.cases.workflow import ResponseCache
from kredpare.core.db import get_engine
from kredpare.core.ingest import ingest_directory
from kredpare.core.matching import DetectedBreak
from kredpare.core.matching.store import run_matching
from kredpare.core.rules.runner import run_rules
from kredpare.core.settings import get_settings
from kredpare.core.tables import Break, ExplanationRow
from kredpare.domains.lending.evals import (
    BREAK_TYPES,
    Key,
    Label,
    RulesScore,
    RuleTally,
    Verdict,
    WorkflowScore,
    WorkflowVerdict,
    actual_keys,
    break_key,
    expected_keys,
    expected_labels,
    score,
    score_rules,
    score_workflow,
)
from kredpare.domains.lending.spec import LENDING

# Development tool: assumes the source checkout (uv workspace), where alembic.ini lives.
_ALEMBIC_INI = Path(__file__).resolve().parents[2] / "alembic.ini"


def _ingest(engine: Engine, directory: Path) -> int:
    outcomes = ingest_directory(engine, LENDING, directory)
    for outcome in outcomes:
        if outcome.status != "ingested" or outcome.errors:
            note = f" ({outcome.message})" if outcome.message else ""
            print(f"{outcome.status:9} {outcome.path}: {outcome.errors} row errors{note}")
    by_status: dict[str, int] = {}
    for outcome in outcomes:
        by_status[outcome.status] = by_status.get(outcome.status, 0) + 1
    rows = sum(o.rows for o in outcomes)
    print(f"{len(outcomes)} files {by_status}, {rows} records stored")
    return 1 if by_status.get("rejected") else 0


def _match(engine: Engine, as_of: date) -> int:
    report = run_matching(engine, LENDING, as_of)
    print(f"{report.detected} breaks detected as of {as_of}, new: {report.created}")
    return 0


@dataclass(frozen=True)
class _WorkflowRuntime:
    llm: LLMClient
    model: str
    threshold: float
    cache: ResponseCache


def _workflow_runtime(model: str | None) -> _WorkflowRuntime | None:
    """The configured LLM client, or None (with a message) when GEMINI_API_KEY is not set."""
    settings = get_settings()
    if settings.llm_api_key is None:
        print("GEMINI_API_KEY is not set: cannot run the workflow level", file=sys.stderr)
        return None
    return _WorkflowRuntime(
        OpenAICompatibleClient.from_settings(settings),
        model or settings.workflow_model,
        settings.workflow_confidence_threshold,
        ResponseCache(settings.workflow_cache_dir),
    )


def _print_workflow_report(report: WorkflowReport, model: str) -> None:
    print(
        f"workflow ({model}): {report.explained} explained, "
        f"{report.needs_investigation} needs_investigation, {report.unavailable} left pending "
        f"(provider unavailable); {report.llm_calls} reached the model "
        f"({report.cached} from cache), {report.short_circuited} short-circuited, "
        f"{report.invalid_outputs} invalid outputs, {report.retries} retries; "
        f"cost ${report.cost_usd:.6f}, spent now ${report.spent_usd:.6f}"
    )
    if report.stopped_by_budget:
        print("stopped early: spend cap reached; rerun to continue", file=sys.stderr)


def _explain(
    engine: Engine,
    *,
    with_workflow: bool = False,
    model: str | None = None,
    llm: _WorkflowRuntime | None = None,
) -> int:
    report = run_rules(engine, LENDING)
    print(
        f"{report.explained} explained, {report.pending_workflow} pending_workflow "
        f"({report.conflicts} rule conflicts); explained by rule: {report.by_rule}"
    )
    if not with_workflow:
        return 0
    runtime = llm or _workflow_runtime(model)
    if runtime is None:
        return 2
    outcome = run_workflow_level(
        engine,
        LENDING,
        llm=runtime.llm,
        model=runtime.model,
        threshold=runtime.threshold,
        cache=runtime.cache,
    )
    _print_workflow_report(outcome, runtime.model)
    return 1 if outcome.unavailable else 0


@contextmanager
def _temporary_database() -> Generator[Engine]:
    """A migrated database next to DATABASE_URL, dropped afterwards.

    Evals need an empty database: audit_events is append-only, so a used one cannot be reset.
    """
    base = make_url(get_settings().database_url)
    name = f"kredpare_eval_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    url = base.set(database=name).render_as_string(hide_password=False)
    engine = create_engine(url)
    try:
        config = Config(str(_ALEMBIC_INI))
        config.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
        command.upgrade(config, "head")
        yield engine
    finally:
        engine.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def _detected(row: RowMapping) -> DetectedBreak:
    return DetectedBreak(
        row["break_type"],
        left_schema=row["left_schema"],
        right_schema=row["right_schema"],
        side_schema=row["side_schema"],
        counterparty_id=row["counterparty_id"],
        batch_id=row["batch_id"],
        record_id=row["record_id"],
        field=row["field"],
    )


def _eval_matching(directory: Path, as_of: date, minimum: float, markdown: bool) -> int:
    with _temporary_database() as engine:
        ingest_directory(engine, LENDING, directory)
        run_matching(engine, LENDING, as_of)
        with engine.connect() as conn:
            rows = conn.execute(select(Break).where(Break.as_of == as_of)).mappings().all()
    found = [_detected(row) for row in rows]
    expected = expected_keys((directory / "ground_truth.jsonl").read_text().splitlines())
    scores = score(expected, actual_keys(found))

    if markdown:
        print("| Break type | Precision | Recall | Support |")
        print("|---|---|---|---|")
    for kind in BREAK_TYPES:
        s = scores[kind]
        if markdown:
            print(f"| `{kind}` | {s.precision:.3f} | {s.recall:.3f} | {s.support} |")
        else:
            print(
                f"{kind:16} precision {s.precision:.3f}  recall {s.recall:.3f}  support {s.support}"
            )
        for key in s.false_positives[:5]:
            print(f"  false positive: {key}", file=sys.stderr)
        for key in s.false_negatives[:5]:
            print(f"  false negative: {key}", file=sys.stderr)

    below = [k for k in BREAK_TYPES if min(scores[k].precision, scores[k].recall) < minimum]
    if below:
        print(f"below {minimum}: {', '.join(below)}", file=sys.stderr)
        return 1
    return 0


def _share(value: float) -> str:
    return f"{value:.3f}"


def _accuracy(tally: RuleTally, value: float) -> str:
    """Accuracy among explained breaks; undefined (not 1.000) when nothing was explained."""
    return _share(value) if tally.explained else "-"


def _print_rules_score(result: RulesScore, markdown: bool) -> None:
    causes = sorted(result.by_cause, key=lambda c: (result.cause_difficulty[c], c))
    tallies: list[tuple[str, str, RuleTally]] = [
        (cause, result.cause_difficulty[cause], result.by_cause[cause]) for cause in causes
    ]
    if markdown:
        print(
            "| Cause | Difficulty | Breaks | Explained | Cause acc. | Side acc. | Proposal acc. |"
        )
        print("|---|---|---|---|---|---|---|")
    for cause, difficulty, t in tallies:
        if markdown:
            print(
                f"| `{cause}` | {difficulty} | {t.support} | {t.explained} | "
                f"{_accuracy(t, t.cause_accuracy)} | {_accuracy(t, t.wrong_side_accuracy)} | "
                f"{_accuracy(t, t.proposal_accuracy)} |"
            )
        else:
            print(
                f"{cause:26} {difficulty:7} breaks {t.support:4}  explained {t.explained:4}  "
                f"cause {_accuracy(t, t.cause_accuracy)}  "
                f"side {_accuracy(t, t.wrong_side_accuracy)}  "
                f"proposal {_accuracy(t, t.proposal_accuracy)}"
            )
    for difficulty in ("simple", "medium", "hard"):
        t = result.by_difficulty.get(difficulty, RuleTally())
        line = (
            f"{difficulty}: {t.explained}/{t.support} explained by rules "
            f"({_share(t.explained_share)}), cause accuracy {_accuracy(t, t.cause_accuracy)}"
        )
        print(f"- {line}" if markdown else line)


def _eval_rules(directory: Path, as_of: date, minimum: float, markdown: bool) -> int:
    with _temporary_database() as engine:
        ingest_directory(engine, LENDING, directory)
        run_matching(engine, LENDING, as_of)
        run_rules(engine, LENDING)
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    select(
                        Break,
                        ExplanationRow.cause,
                        ExplanationRow.wrong_side,
                        ExplanationRow.proposal,
                    )
                    .join(ExplanationRow, ExplanationRow.break_id == Break.id, isouter=True)
                    .where(Break.as_of == as_of)
                )
                .mappings()
                .all()
            )
    verdicts: dict[Key, Verdict] = {}
    for row in rows:
        if row["cause"] is not None:
            verdicts[break_key(_detected(row))] = Verdict(
                row["cause"], row["wrong_side"], row["proposal"]
            )
    labels = expected_labels((directory / "ground_truth.jsonl").read_text().splitlines())
    result = score_rules(labels, verdicts)

    _print_rules_score(result, markdown)
    for key in result.false_claims[:5]:
        print(f"  medium/hard break explained by a rule: {key}", file=sys.stderr)
    for key in result.unlabeled_explained[:5]:
        print(f"  explained break without ground truth: {key}", file=sys.stderr)
    summary = f"S2 {_share(result.s2)} (target >= {minimum}), S3 {result.s3} (target 0)"
    print(f"\n{summary}")

    failed = result.s2 < minimum or result.s3 > 0
    if failed:
        print(f"rules eval failed: {summary}", file=sys.stderr)
    return 1 if failed else 0


def _rule_verdicts(engine: Engine, as_of: date) -> dict[Key, Verdict]:
    with engine.connect() as conn:
        rows = (
            conn.execute(
                select(
                    Break, ExplanationRow.cause, ExplanationRow.wrong_side, ExplanationRow.proposal
                )
                .join(ExplanationRow, ExplanationRow.break_id == Break.id)
                .where(Break.as_of == as_of, ExplanationRow.level == "rule")
            )
            .mappings()
            .all()
        )
    return {
        break_key(_detected(row)): Verdict(row["cause"], row["wrong_side"], row["proposal"])
        for row in rows
    }


def _eval_workflow(
    directory: Path,
    as_of: date,
    model: str | None,
    markdown: bool,
    max_spend: Decimal,
    *,
    runtime: _WorkflowRuntime | None = None,
) -> int:
    runtime = runtime or _workflow_runtime(model)
    if runtime is None:
        return 2
    labels = expected_labels((directory / "ground_truth.jsonl").read_text().splitlines())
    with _temporary_database() as engine:
        ingest_directory(engine, LENDING, directory)
        run_matching(engine, LENDING, as_of)
        run_rules(engine, LENDING)
        rules = score_rules(labels, _rule_verdicts(engine, as_of))
        report = run_workflow_level(
            engine,
            LENDING,
            llm=runtime.llm,
            model=runtime.model,
            threshold=runtime.threshold,
            cache=runtime.cache,
            max_spend_usd=max_spend,
        )
        with engine.connect() as conn:
            rows = {
                row["id"]: row
                for row in conn.execute(select(Break).where(Break.as_of == as_of)).mappings()
            }
    verdicts: dict[Key, WorkflowVerdict] = {}
    for outcome in report.outcomes:
        result = outcome.result
        explanation = result.explanation if result.status.value == "explained" else None
        verdicts[break_key(_detected(rows[outcome.break_id]))] = WorkflowVerdict(
            status=result.status.value,
            cause=explanation.cause if explanation else None,
            wrong_side=explanation.wrong_side if explanation else None,
            proposal=explanation.proposal if explanation else None,
            citations=tuple(explanation.citations) if explanation else (),
            llm_called=result.usage.llm_called,
            cost_usd=result.usage.cost_usd,
            latency_seconds=result.usage.latency_seconds,
            invalid_output=any(r.startswith("invalid_model_output") for r in result.reasons),
        )
    scored = score_workflow(labels, verdicts)
    _print_workflow_score(runtime.model, scored, rules, report, markdown)
    _print_failures(labels, verdicts, report, rows)
    return 1 if report.unavailable or report.stopped_by_budget else 0


def _print_workflow_score(
    model: str, w: WorkflowScore, rules: RulesScore, report: WorkflowReport, markdown: bool
) -> None:
    lines = [
        f"S4 root cause accuracy (medium, n={w.medium_support}): {_share(w.s4)}",
        f"S5 citation accuracy, exact set (medium): {_share(w.s5)}",
        f"S5 citation accuracy, expected cited (extra allowed): {_share(w.s5_superset)}",
        f"wrong side accuracy (medium): {_share(w.wrong_side_accuracy)}",
        f"S6 hard routed to needs_investigation (n={w.hard_support}): {_share(w.s6)}",
        f"S7 cost per break reaching the workflow: ${w.cost_per_break:.6f} "
        f"(n={w.reached_workflow}; {w.llm_calls} called the LLM, {w.short_circuited} "
        f"short-circuited; ${w.cost_per_call:.6f} per call; total ${w.total_cost:.6f}; "
        f"spent now ${report.spent_usd:.6f})",
        f"latency p50 / p95: {w.latency_p50:.2f}s / {w.latency_p95:.2f}s",
        f"invalid outputs: {w.invalid_outputs}; retries: {report.retries}; "
        f"unavailable: {report.unavailable}; from cache: {report.cached}",
        f"rule level (regression check): S2 {_share(rules.s2)} (target >= 0.9), S3 {rules.s3} "
        "(target 0)",
    ]
    if markdown:
        print(
            f"| {model} | {_share(w.s4)} | {_share(w.s5)} | {_share(w.s6)} | "
            f"${w.cost_per_break:.6f} | | |"
        )
        print()
        lines = [f"- {line}" for line in lines]
    print("\n".join(lines))


def _print_failures(
    labels: dict[Key, Label],
    verdicts: dict[Key, WorkflowVerdict],
    report: WorkflowReport,
    rows: dict[uuid.UUID, RowMapping],
) -> None:
    """Up to 5 medium breaks the workflow got wrong or left, with the reasons."""
    shown = 0
    for outcome in report.outcomes:
        key = break_key(_detected(rows[outcome.break_id]))
        label = labels.get(key)
        verdict = verdicts[key]
        if label is None or label.difficulty != "medium":
            continue
        wrong = verdict.status != "explained" or verdict.cause != label.cause
        if not wrong or shown >= 5:
            continue
        shown += 1
        print(
            f"  medium miss {key}: expected {label.cause} {label.citations}; "
            f"got {verdict.status} {verdict.cause} {verdict.citations}; "
            f"reasons {outcome.result.reasons}",
            file=sys.stderr,
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kredpare", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="load a kredpare-datagen output directory")
    ingest.add_argument("directory", type=Path)

    match = commands.add_parser("match", help="detect breaks over all stored records")
    match.add_argument("--as-of", type=date.fromisoformat, required=True)

    explain = commands.add_parser("explain", help="run the rule level, then the workflow level")
    explain.add_argument("--no-workflow", action="store_true", help="skip the LLM level")
    explain.add_argument("--model", help="workflow model id (default: WORKFLOW_MODEL)")

    evals = commands.add_parser("eval", help="measure against ground truth")
    which = evals.add_subparsers(dest="eval", required=True)
    matching = which.add_parser("matching", help="break detection, in a temporary database")
    matching.add_argument("directory", type=Path)
    matching.add_argument("--as-of", type=date.fromisoformat, required=True)
    matching.add_argument("--min", type=float, default=0.98, help="fail below this score")
    matching.add_argument("--markdown", action="store_true", help="print a docs/evals.md table")
    rules = which.add_parser("rules", help="rule explanations, in a temporary database")
    rules.add_argument("directory", type=Path)
    rules.add_argument("--as-of", type=date.fromisoformat, required=True)
    rules.add_argument("--min", type=float, default=0.90, help="S2: fail below this share")
    rules.add_argument("--markdown", action="store_true", help="print docs/evals.md tables")
    workflow = which.add_parser("workflow", help="workflow explanations, in a temporary database")
    workflow.add_argument("directory", type=Path)
    workflow.add_argument("--as-of", type=date.fromisoformat, required=True)
    workflow.add_argument("--model", help="model id (default: WORKFLOW_MODEL)")
    workflow.add_argument(
        "--max-spend", type=Decimal, default=Decimal("1.00"), help="stop above this many USD"
    )
    workflow.add_argument("--markdown", action="store_true", help="print a docs/evals.md row")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "ingest":
        return _ingest(get_engine(), args.directory)
    if args.command == "match":
        return _match(get_engine(), args.as_of)
    if args.command == "explain":
        return _explain(get_engine(), with_workflow=not args.no_workflow, model=args.model)
    if args.eval == "workflow":
        return _eval_workflow(args.directory, args.as_of, args.model, args.markdown, args.max_spend)
    if args.eval == "rules":
        return _eval_rules(args.directory, args.as_of, args.min, args.markdown)
    return _eval_matching(args.directory, args.as_of, args.min, args.markdown)
