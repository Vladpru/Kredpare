"""End to end: datagen output → ingest, matching, rules → eval against ground truth (S2, S3).

Needs the database from `make up` (DATABASE_URL); the eval creates and drops its own database.
"""

import json
from pathlib import Path

import pytest
from kredpare.cli import main as kredpare

from kredpare_datagen.cli import main as datagen

AS_OF = "2026-09-08"


@pytest.fixture(scope="module")
def dataset(tmp_path_factory: pytest.TempPathFactory) -> Path:
    out = tmp_path_factory.mktemp("dataset")
    assert datagen(["--seed", "42", "--out", str(out)]) == 0
    return out


def _relabeled(dataset: Path, tmp_path: Path, change: dict[str, str]) -> Path:
    """The same dataset with the difficulty of the given causes changed in ground truth."""
    copy = tmp_path / "relabeled"
    copy.mkdir()
    for item in dataset.iterdir():
        if item.name != "ground_truth.jsonl":
            (copy / item.name).symlink_to(item)
    lines: list[str] = []
    for line in (dataset / "ground_truth.jsonl").read_text().splitlines():
        record = json.loads(line)
        record["difficulty"] = change.get(record["cause"], record["difficulty"])
        lines.append(json.dumps(record))
    (copy / "ground_truth.jsonl").write_text("\n".join(lines) + "\n")
    return copy


def test_rules_meet_s2_and_s3(dataset: Path) -> None:
    assert kredpare(["eval", "rules", str(dataset), "--as-of", AS_OF]) == 0


def test_eval_fails_when_a_simple_cause_is_not_closed_by_rules(
    dataset: Path, tmp_path: Path
) -> None:
    # Medium breaks counted as simple are never explained by rules: S2 falls below 0.90.
    relabeled = _relabeled(
        dataset, tmp_path, {"accrued_interest_error": "simple", "price_grid_amendment": "simple"}
    )

    assert kredpare(["eval", "rules", str(relabeled), "--as-of", AS_OF]) == 1


def test_eval_fails_when_a_rule_claims_a_medium_break(dataset: Path, tmp_path: Path) -> None:
    # Rule-closed breaks counted as medium are a rule claiming a medium break: S3 > 0.
    relabeled = _relabeled(dataset, tmp_path, {"rounding_difference": "medium"})

    assert kredpare(["eval", "rules", str(relabeled), "--as-of", AS_OF]) == 1
