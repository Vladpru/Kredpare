import hashlib
import json
from pathlib import Path

import pytest

from kredpare_datagen.cli import main


def _run(out: Path, *extra: str) -> int:
    return main(["--seed", "42", "--days", "30", "--out", str(out), *extra])


def test_writes_csvs_manifest_and_ground_truth(tmp_path: Path) -> None:
    out = tmp_path / "data"

    assert _run(out) == 0

    manifest = [json.loads(line) for line in (out / "manifest.jsonl").read_text().splitlines()]
    truth = [json.loads(line) for line in (out / "ground_truth.jsonl").read_text().splitlines()]
    assert len(truth) == 94
    assert {m["schema_name"] for m in manifest} == {
        "FundedLoan",
        "PurchaseConfirmation",
        "ServicerOnboarding",
    }
    for entry in manifest:
        content = (out / entry["path"]).read_bytes()
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]
    assert sorted(str(p.relative_to(out)) for p in out.rglob("*.csv")) == sorted(
        m["path"] for m in manifest
    )


def test_ground_truth_lines_follow_the_documented_format(tmp_path: Path) -> None:
    _run(tmp_path)
    first = json.loads((tmp_path / "ground_truth.jsonl").read_text().splitlines()[0])

    assert list(first) == [
        "break_id",
        "counterparty_id",
        "batch_ids",
        "loan_ids",
        "break_type",
        "fields",
        "missing_side",
        "cause",
        "difficulty",
        "wrong_side",
        "expected_level",
        "expected_citations",
        "expected_proposal",
    ]


def test_window_start_is_configurable(tmp_path: Path) -> None:
    _run(tmp_path, "--start", "2026-08-17", "--clean")
    manifest = (tmp_path / "manifest.jsonl").read_text()

    assert "cp-quillmont-2026-08-12" not in manifest
    assert "cp-quillmont-2026-08-19" in manifest


def test_clean_writes_empty_ground_truth(tmp_path: Path) -> None:
    _run(tmp_path, "--clean")

    assert (tmp_path / "ground_truth.jsonl").read_text() == ""


def test_refuses_a_non_empty_output_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "keep.txt").write_text("mine")

    assert _run(tmp_path) == 2
    assert "not empty" in capsys.readouterr().err
    assert [p.name for p in tmp_path.iterdir()] == ["keep.txt"]


@pytest.mark.parametrize("args", [["--days", "0"], ["--loans-per-batch", "3"]])
def test_rejects_invalid_arguments(tmp_path: Path, args: list[str]) -> None:
    with pytest.raises(SystemExit) as exit_info:
        main(["--out", str(tmp_path / "x"), *args])

    assert exit_info.value.code == 2
