from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def _load_exporter():
    path = Path(__file__).parents[1] / "scripts" / "build_huggingface_export.py"
    spec = importlib.util.spec_from_file_location("build_huggingface_export", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_build_huggingface_export(dataset_dir: Path) -> None:
    exporter = _load_exporter()
    output, rows = exporter.build_export(dataset_dir)
    parsed = [json.loads(line) for line in output.read_text(encoding="utf-8").splitlines()]
    manifest = json.loads((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    manifest_paths = {row["path"] for row in manifest["files"]}
    assert rows == 1
    assert parsed[0]["task_id"] == "task_0001"
    assert set(parsed[0]) == {"task_id", "prompt", "input", "expected_answer"}
    assert "data/tasks.jsonl" in manifest_paths
