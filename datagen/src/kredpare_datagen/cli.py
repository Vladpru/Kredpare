"""kredpare-datagen: write a reproducible synthetic dataset with labeled breaks."""

import argparse
import hashlib
import json
import sys
from collections import Counter
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

from kredpare_datagen.agreements import TIERS
from kredpare_datagen.formats import render_dataset
from kredpare_datagen.generate import generate_clean
from kredpare_datagen.ground_truth import GroundTruth
from kredpare_datagen.inject import inject

DEFAULT_START = date(2026, 8, 10)


def _at_least(minimum: int) -> Callable[[str], int]:
    def parse(text: str) -> int:
        value = int(text)
        if value < minimum:
            raise argparse.ArgumentTypeError(f"must be at least {minimum}, got {value}")
        return value

    return parse


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="kredpare-datagen", description=__doc__)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--days", type=_at_least(1), default=30, help="window length in days")
    parser.add_argument(
        "--start", type=date.fromisoformat, default=DEFAULT_START, help="first day, YYYY-MM-DD"
    )
    parser.add_argument("--out", type=Path, default=Path("data/generated"))
    parser.add_argument("--loans-per-batch", type=_at_least(len(TIERS)), default=40)
    parser.add_argument("--clean", action="store_true", help="no breaks, empty ground truth")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    out: Path = args.out
    if out.exists() and any(out.iterdir()):
        print(f"kredpare-datagen: output directory {out} is not empty", file=sys.stderr)
        return 2

    dataset = generate_clean(args.seed, args.start, args.days, args.loans_per_batch)
    truth: list[GroundTruth] = []
    if not args.clean:
        dataset, truth = inject(dataset)

    manifest: list[str] = []
    for file in render_dataset(dataset):
        content = file.content.encode()
        path = out / file.path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        manifest.append(
            json.dumps(
                {
                    "path": file.path,
                    "counterparty_id": file.counterparty_id,
                    "schema_name": file.schema_name,
                    "batch_id": file.batch_id,
                    "sha256": hashlib.sha256(content).hexdigest(),
                }
            )
        )
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.jsonl").write_bytes("".join(f"{line}\n" for line in manifest).encode())
    (out / "ground_truth.jsonl").write_bytes(
        "".join(f"{record.model_dump_json()}\n" for record in truth).encode()
    )

    causes = Counter(record.difficulty for record in truth)
    print(
        f"wrote {len(manifest)} files and {len(truth)} ground truth records to {out} "
        f"(simple {causes['simple']}, medium {causes['medium']}, hard {causes['hard']})"
    )
    return 0
