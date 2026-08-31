from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from conftest import MODEL_ANSWER

from cab.config import PipelineConfig
from cab.evaluation import evaluate_run
from cab.reporting import generate_leaderboard, generate_report
from cab.runner import latest_artifact, run_pipeline


def test_run_resume_evaluate_and_report(dataset_dir: Path, tmp_path: Path) -> None:
    model_script = tmp_path / "model.py"
    model_script.write_text(
        "import json,sys\nsys.stdin.read()\nprint(json.dumps(" + repr(MODEL_ANSWER) + "))\n",
        encoding="utf-8",
    )
    output = tmp_path / "output"
    pipeline = PipelineConfig(
        name="fixture-model",
        provider="command",
        model="fixture",
        command=(sys.executable, str(model_script)),
        retries=1,
    )
    first = run_pipeline(
        pipeline,
        data_dir=dataset_dir,
        output_dir=output,
        attempts=2,
        max_concurrent=2,
    )
    assert first["ok"] == 2
    assert first["failed"] == 0
    run_metadata = json.loads((Path(first["run_dir"]) / "run.json").read_text(encoding="utf-8"))
    assert run_metadata["dataset"]["repo_id"] == "owner/dataset"
    assert run_metadata["dataset"]["requested_revision"] == "main"
    assert run_metadata["dataset"]["resolved_revision"] == "abc123"
    assert len(run_metadata["pipeline_sha256"]) == 64

    summary = evaluate_run(first["run_dir"], dataset_dir)
    assert summary["mean_score"] == 1.0
    assert summary["pass_at_k"] == 1.0
    assert summary["exact_at_k"] == 1.0

    report = generate_report(first["run_dir"])
    leaderboard = generate_leaderboard(output)
    assert "fixture" in report.read_text(encoding="utf-8")
    assert "fixture-model" in leaderboard.read_text(encoding="utf-8")

    second = run_pipeline(
        pipeline,
        data_dir=dataset_dir,
        output_dir=output,
        attempts=2,
        max_concurrent=2,
    )
    assert second["skipped"] == 2
    assert len(list((Path(first["run_dir"]) / "answers").rglob("attempt_*.json"))) == 2


def test_generated_summary_is_json(dataset_dir: Path, tmp_path: Path) -> None:
    model_script = tmp_path / "model.py"
    model_script.write_text(
        "import json,sys\nsys.stdin.read()\nprint(json.dumps(" + repr(MODEL_ANSWER) + "))\n",
        encoding="utf-8",
    )
    pipeline = PipelineConfig(
        name="json-model",
        provider="command",
        model="fixture",
        command=(sys.executable, str(model_script)),
        retries=1,
    )
    run = run_pipeline(pipeline, data_dir=dataset_dir, output_dir=tmp_path / "out", attempts=1)
    evaluate_run(run["run_dir"], dataset_dir)
    parsed = json.loads((Path(run["run_dir"]) / "summary.json").read_text(encoding="utf-8"))
    assert parsed["schema"] == "cab-public-evaluation"
    assert parsed["scorer"] == "cab-public-deterministic"


def test_resume_rejects_changed_system_prompt(dataset_dir: Path, tmp_path: Path) -> None:
    model_script = tmp_path / "model.py"
    model_script.write_text(
        "import json,sys\nsys.stdin.read()\nprint(json.dumps(" + repr(MODEL_ANSWER) + "))\n",
        encoding="utf-8",
    )
    common = {
        "name": "identity-model",
        "provider": "command",
        "model": "fixture",
        "command": (sys.executable, str(model_script)),
        "retries": 1,
    }
    output = tmp_path / "out"
    run_pipeline(
        PipelineConfig(**common, system_prompt="First."),
        data_dir=dataset_dir,
        output_dir=output,
        attempts=1,
    )
    with pytest.raises(ValueError, match="different pipeline configuration"):
        run_pipeline(
            PipelineConfig(**common, system_prompt="Second."),
            data_dir=dataset_dir,
            output_dir=output,
            attempts=1,
        )


def test_attempt_one_never_matches_attempt_ten(tmp_path: Path) -> None:
    task_output = tmp_path / "answers" / "task_0001"
    task_output.mkdir(parents=True)
    (task_output / "attempt_1.json").write_text('{"attempt": 1}\n', encoding="utf-8")
    (task_output / "attempt_10.json").write_text('{"attempt": 10}\n', encoding="utf-8")
    assert latest_artifact(task_output, 1) == {"attempt": 1}


def _summary(name: str, sha: str, attempts: int, mean: float) -> dict:
    return {
        "run_name": name,
        "pipeline": {"model": name, "provider": "command"},
        "dataset": {"dataset_sha256": sha, "resolved_revision": "abc123"},
        "tasks": 123,
        "attempts_per_task": attempts,
        "mean_score": mean,
        "pass_at_k": mean,
        "exact_at_k": mean,
    }


def test_leaderboard_marks_runs_from_a_different_snapshot(tmp_path: Path) -> None:
    output = tmp_path / "out"
    for row in (
        _summary("run-high", "aaaa", 3, 0.9),
        _summary("run-low", "aaaa", 3, 0.4),
        _summary("run-other-snapshot", "bbbb", 3, 0.6),
        _summary("run-other-attempts", "aaaa", 1, 0.5),
    ):
        run_dir = output / row["run_name"]
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(json.dumps(row), encoding="utf-8")

    page = generate_leaderboard(output).read_text(encoding="utf-8")

    assert "not directly comparable" in page
    assert page.count("different snapshot") == 2
    assert page.index("run-high") < page.index("run-other-snapshot") < page.index("run-low")


def test_leaderboard_stays_quiet_when_every_run_matches(tmp_path: Path) -> None:
    output = tmp_path / "out"
    for row in (_summary("a", "aaaa", 3, 0.9), _summary("b", "aaaa", 3, 0.4)):
        run_dir = output / row["run_name"]
        run_dir.mkdir(parents=True)
        (run_dir / "summary.json").write_text(json.dumps(row), encoding="utf-8")

    page = generate_leaderboard(output).read_text(encoding="utf-8")

    assert "not directly comparable" not in page
    assert "different snapshot" not in page
