from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from statistics import fmean
from typing import Any

from .runner import latest_artifact
from .scoring import SCORER_ID, evaluate_answer
from .utils import atomic_write_json, load_json, utc_now


def _average(values: list[float | bool]) -> float:
    return round(fmean(float(value) for value in values), 6) if values else 0.0


def evaluate_run(run_dir: str | Path, data_dir: str | Path = "data") -> dict[str, Any]:
    run_path = Path(run_dir)
    metadata = load_json(run_path / "run.json")
    attempts = int(metadata["attempts"])
    per_task: list[dict[str, Any]] = []
    all_attempts: list[dict[str, Any]] = []

    for task_id in metadata["task_ids"]:
        expected_path = Path(data_dir) / "tasks" / task_id / "expected_answer.json"
        expected = load_json(expected_path)
        rows = []
        for attempt in range(1, attempts + 1):
            artifact = latest_artifact(run_path / "answers" / task_id, attempt)
            parsed = artifact.get("parsed_answer") if artifact and not artifact.get("error") else None
            evaluation = evaluate_answer(parsed, expected)
            row = {
                "task_id": task_id,
                "family": expected["rubric"]["family"],
                "attempt": attempt,
                "missing": artifact is None,
                "error": artifact.get("error") if artifact else "MISSING_ATTEMPT",
                **evaluation,
            }
            rows.append(row)
            all_attempts.append(row)
            atomic_write_json(
                run_path / "evaluations" / task_id / f"attempt_{attempt}.json", row
            )
        best = max(rows, key=lambda row: (row["score"], row["exact_match"], row["passed"]))
        per_task.append(
            {
                "task_id": task_id,
                "family": expected["rubric"]["family"],
                "best_score": best["score"],
                "passed_at_k": any(row["passed"] for row in rows),
                "exact_at_k": any(row["exact_match"] for row in rows),
                "attempts": rows,
            }
        )

    by_family_rows: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in per_task:
        by_family_rows[row["family"]].append(row)
    by_family = {
        family: {
            "tasks": len(rows),
            "best_at_k": _average([row["best_score"] for row in rows]),
            "pass_at_k": _average([row["passed_at_k"] for row in rows]),
            "exact_at_k": _average([row["exact_at_k"] for row in rows]),
        }
        for family, rows in sorted(by_family_rows.items())
    }
    summary = {
        "schema": "cab-public-evaluation",
        "run_name": metadata["run_name"],
        "pipeline": metadata["pipeline"],
        "dataset": metadata["dataset"],
        "score_source": "public_deterministic_lower_bound",
        "scorer": SCORER_ID,
        "answer_key_access": "public",
        "result_trust": "self_reported_educational",
        "tasks": len(per_task),
        "attempts_per_task": attempts,
        "attempts_expected": len(per_task) * attempts,
        "attempts_completed": sum(not row["missing"] for row in all_attempts),
        "mean_score": _average([row["score"] for row in all_attempts]),
        "best_at_k": _average([row["best_score"] for row in per_task]),
        "pass_at_k": _average([row["passed_at_k"] for row in per_task]),
        "exact_at_k": _average([row["exact_at_k"] for row in per_task]),
        "deciding_account_at_k": _average(
            [any(attempt["facts"]["deciding_account"] for attempt in row["attempts"]) for row in per_task]
        ),
        "wallet_account_at_k": _average(
            [any(attempt["facts"]["wallet_account"] for attempt in row["attempts"]) for row in per_task]
        ),
        "amount_at_k": _average(
            [any(attempt["facts"]["amounts"] for attempt in row["attempts"]) for row in per_task]
        ),
        "drcr_at_k": _average(
            [any(attempt["facts"]["drcr"] for attempt in row["attempts"]) for row in per_task]
        ),
        "quantity_at_k": _average(
            [any(attempt["facts"]["quantity"] for attempt in row["attempts"]) for row in per_task]
        ),
        "balanced_at_k": _average(
            [any(attempt["facts"]["balanced"] for attempt in row["attempts"]) for row in per_task]
        ),
        "by_family": by_family,
        "completed_at": utc_now(),
        "per_task": per_task,
    }
    atomic_write_json(run_path / "summary.json", summary)
    return summary
