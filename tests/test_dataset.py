from __future__ import annotations

import json
from pathlib import Path

import pytest

from cab.dataset import dataset_digest, verify_dataset


def test_verify_dataset_and_digest(dataset_dir: Path) -> None:
    result = verify_dataset(dataset_dir)
    assert result["ok"] is True
    assert result["tasks"] == 1
    assert result["task_file_hashes_checked"] == 3
    assert result["dataset_sha256"] == dataset_digest(dataset_dir)
    assert result["repo_id"] == "owner/dataset"
    assert result["requested_revision"] == "main"
    assert result["resolved_revision"] == "abc123"


def test_digest_moves_when_prompt_moves(dataset_dir: Path) -> None:
    before = dataset_digest(dataset_dir)
    prompt = dataset_dir / "tasks" / "task_0001" / "prompt.md"
    prompt.write_text("Changed prompt\n", encoding="utf-8")
    assert dataset_digest(dataset_dir) != before


def test_verify_rejects_missing_manifest_checksum(dataset_dir: Path) -> None:
    manifest_path = dataset_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [
        row for row in manifest["files"] if row["path"] != "tasks/task_0001/prompt.md"
    ]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="missing manifest checksum"):
        verify_dataset(dataset_dir)


def test_verify_rejects_task_id_substitution(dataset_dir: Path) -> None:
    (dataset_dir / "tasks" / "task_0001").rename(dataset_dir / "tasks" / "task_9999")
    with pytest.raises(ValueError, match="missing task directories"):
        verify_dataset(dataset_dir)
