"""kredpare: ingest files, run matching, and measure break detection.

The composition root: the only place that picks a domain (lending) and hands it to core.
"""

import argparse
import sys
import uuid
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, make_url, select, text

from kredpare.core.db import get_engine
from kredpare.core.ingest import ingest_directory
from kredpare.core.matching import DetectedBreak
from kredpare.core.matching.store import run_matching
from kredpare.core.settings import get_settings
from kredpare.core.tables import Break
from kredpare.domains.lending.evals import BREAK_TYPES, actual_keys, expected_keys, score
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


def _eval_matching(directory: Path, as_of: date, minimum: float, markdown: bool) -> int:
    with _temporary_database() as engine:
        ingest_directory(engine, LENDING, directory)
        run_matching(engine, LENDING, as_of)
        with engine.connect() as conn:
            rows = conn.execute(select(Break).where(Break.as_of == as_of)).mappings().all()
    found = [
        DetectedBreak(
            row["break_type"],
            left_schema=row["left_schema"],
            right_schema=row["right_schema"],
            side_schema=row["side_schema"],
            counterparty_id=row["counterparty_id"],
            batch_id=row["batch_id"],
            record_id=row["record_id"],
            field=row["field"],
        )
        for row in rows
    ]
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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kredpare", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    ingest = commands.add_parser("ingest", help="load a kredpare-datagen output directory")
    ingest.add_argument("directory", type=Path)

    match = commands.add_parser("match", help="detect breaks over all stored records")
    match.add_argument("--as-of", type=date.fromisoformat, required=True)

    evals = commands.add_parser("eval", help="measure against ground truth")
    which = evals.add_subparsers(dest="eval", required=True)
    matching = which.add_parser("matching", help="break detection, in a temporary database")
    matching.add_argument("directory", type=Path)
    matching.add_argument("--as-of", type=date.fromisoformat, required=True)
    matching.add_argument("--min", type=float, default=0.98, help="fail below this score")
    matching.add_argument("--markdown", action="store_true", help="print a docs/evals.md table")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "ingest":
        return _ingest(get_engine(), args.directory)
    if args.command == "match":
        return _match(get_engine(), args.as_of)
    return _eval_matching(args.directory, args.as_of, args.min, args.markdown)
