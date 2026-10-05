"""End to end: datagen output → kredpare ingest and matching → eval against ground truth.

Needs the database from `make up` (DATABASE_URL); the eval creates and drops its own database.
"""

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


def test_matching_meets_the_s1_target(dataset: Path) -> None:
    assert kredpare(["eval", "matching", str(dataset), "--as-of", AS_OF]) == 0


def test_eval_fails_when_ground_truth_disagrees(dataset: Path, tmp_path: Path) -> None:
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    for item in dataset.iterdir():
        (tampered / item.name).symlink_to(item)
    (tampered / "ground_truth.jsonl").unlink()
    # Drop every stale_pending label: matching still finds them, so precision falls to 0.
    lines = (dataset / "ground_truth.jsonl").read_text().splitlines()
    kept = [line for line in lines if '"stale_pending"' not in line]
    assert len(kept) < len(lines)
    (tampered / "ground_truth.jsonl").write_text("\n".join(kept) + "\n")

    assert kredpare(["eval", "matching", str(tampered), "--as-of", AS_OF]) == 1
