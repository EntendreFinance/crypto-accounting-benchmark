from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from .config import PipelineConfig
from .dataset import task_directories, verify_dataset
from .providers import Provider, call_with_retries, create_provider
from .scoring import parse_answer
from .utils import atomic_write_json, load_json, sha256_bytes, sha256_json, utc_now

RUN_SCHEMA = "cab-public-run"


def _artifact_paths(task_output: Path, attempt: int) -> list[Path]:
    base = task_output / f"attempt_{attempt}.json"
    paths = [base] if base.is_file() else []
    retries = []
    pattern = re.compile(rf"attempt_{attempt}\.retry_(\d+)\.json")
    for path in task_output.glob(f"attempt_{attempt}.retry_*.json"):
        match = pattern.fullmatch(path.name)
        if match:
            retries.append((int(match.group(1)), path))
    paths.extend(path for _, path in sorted(retries))
    return paths


def _next_artifact_path(task_output: Path, attempt: int) -> Path:
    base = task_output / f"attempt_{attempt}.json"
    if not base.exists():
        return base
    retry = 1
    while (candidate := task_output / f"attempt_{attempt}.retry_{retry}.json").exists():
        retry += 1
    return candidate


def latest_artifact(task_output: Path, attempt: int) -> dict[str, Any] | None:
    paths = _artifact_paths(task_output, attempt)
    if not paths:
        return None
    return load_json(paths[-1])


def _usable(
    artifact: dict[str, Any] | None,
    dataset_sha: str,
    pipeline_sha: str,
    effective_prompt_sha: str,
) -> bool:
    return bool(
        artifact
        and not artifact.get("error")
        and artifact.get("parsed_answer")
        and artifact.get("dataset_sha256") == dataset_sha
        and artifact.get("pipeline_sha256") == pipeline_sha
        and artifact.get("effective_prompt_sha256") == effective_prompt_sha
    )


def run_pipeline(
    pipeline: PipelineConfig,
    *,
    data_dir: str | Path = "data",
    output_dir: str | Path = "output",
    run_name: str | None = None,
    attempts: int = 3,
    max_concurrent: int = 1,
    limit: int | None = None,
    task_ids: list[str] | None = None,
) -> dict[str, Any]:
    if attempts < 1 or max_concurrent < 1:
        raise ValueError("attempts and max_concurrent must be at least 1")
    verification = verify_dataset(data_dir)
    dataset_sha = verification["dataset_sha256"]
    pipeline_identity = pipeline.public_dict()
    pipeline_sha = sha256_json(pipeline_identity)
    tasks = task_directories(data_dir)
    if task_ids:
        wanted = set(task_ids)
        tasks = [path for path in tasks if path.name in wanted]
        missing = sorted(wanted - {path.name for path in tasks})
        if missing:
            raise ValueError(f"Unknown task ids: {', '.join(missing)}")
    if limit is not None:
        tasks = tasks[:limit]
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", run_name or pipeline.name).strip("-")
    if not safe_name:
        raise ValueError("run name must contain at least one letter or number")
    run_dir = Path(output_dir) / safe_name
    answers_dir = run_dir / "answers"
    metadata_path = run_dir / "run.json"
    metadata = {
        "schema": RUN_SCHEMA,
        "run_name": safe_name,
        "pipeline": pipeline_identity,
        "pipeline_sha256": pipeline_sha,
        "dataset": {
            "repo_id": verification.get("repo_id"),
            "dataset_sha256": dataset_sha,
            "requested_revision": verification.get("requested_revision"),
            "resolved_revision": verification.get("resolved_revision"),
        },
        "task_ids": [path.name for path in tasks],
        "task_count": len(tasks),
        "attempts": attempts,
        "max_concurrent": max_concurrent,
        "created_at": utc_now(),
    }
    if metadata_path.exists():
        existing = load_json(metadata_path)
        if existing.get("pipeline") != metadata["pipeline"]:
            raise ValueError(
                f"{run_dir} belongs to a different pipeline configuration. Use --run-name."
            )
        if existing.get("dataset", {}).get("dataset_sha256") != dataset_sha:
            raise ValueError(
                f"{run_dir} belongs to a different dataset snapshot. Use a new --run-name."
            )
        if existing.get("task_ids") != metadata["task_ids"] or existing.get("attempts") != attempts:
            raise ValueError(
                f"{run_dir} has a different task/attempt plan. Resume with the original options "
                "or use a new --run-name."
            )
        metadata = existing
    else:
        atomic_write_json(metadata_path, metadata)

    provider: Provider = create_provider(pipeline)
    pending: list[tuple[Path, int, str, str, str]] = []
    skipped = 0
    for task_dir in tasks:
        prompt = (task_dir / "prompt.md").read_text(encoding="utf-8")
        task_prompt_sha = sha256_bytes(prompt.encode("utf-8"))
        effective_prompt_sha = sha256_json(
            {
                "system_role": pipeline.system_role,
                "system_prompt": pipeline.system_prompt,
                "task_prompt": prompt,
            }
        )
        task_output = answers_dir / task_dir.name
        for attempt in range(1, attempts + 1):
            if _usable(
                latest_artifact(task_output, attempt),
                dataset_sha,
                pipeline_sha,
                effective_prompt_sha,
            ):
                skipped += 1
            else:
                pending.append((task_dir, attempt, prompt, task_prompt_sha, effective_prompt_sha))

    def run_one(item: tuple[Path, int, str, str, str]) -> dict[str, Any]:
        task_dir, attempt, prompt, task_prompt_sha, effective_prompt_sha = item
        started_at = utc_now()
        started = time.perf_counter()
        response = None
        parsed = None
        error = None
        try:
            response = call_with_retries(provider, prompt)
            parsed = parse_answer(response.text)
        except Exception as exc:  # noqa: BLE001 - every failed call remains an artifact
            error = f"{type(exc).__name__}: {exc}"
        artifact = {
            "schema": RUN_SCHEMA,
            "task_id": task_dir.name,
            "attempt": attempt,
            "pipeline_name": pipeline.name,
            "provider": pipeline.provider,
            "model": pipeline.model,
            "dataset_sha256": dataset_sha,
            "pipeline_sha256": pipeline_sha,
            "task_prompt_sha256": task_prompt_sha,
            "effective_prompt_sha256": effective_prompt_sha,
            "started_at": started_at,
            "completed_at": utc_now(),
            "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            "response_id": response.response_id if response else None,
            "input_tokens": response.input_tokens if response else None,
            "output_tokens": response.output_tokens if response else None,
            "raw_response": response.text if response else "",
            "parsed_answer": parsed,
            "error": error,
        }
        task_output = answers_dir / task_dir.name
        path = _next_artifact_path(task_output, attempt)
        atomic_write_json(path, artifact)
        return artifact

    ok = failed = 0
    completed = skipped
    total = len(tasks) * attempts
    if skipped:
        print(f"[cab] resume: {skipped}/{total} completed attempts reused", flush=True)
    with ThreadPoolExecutor(max_workers=max_concurrent) as executor:
        futures = {executor.submit(run_one, item): (item[0].name, item[1]) for item in pending}
        for future in as_completed(futures):
            artifact = future.result()
            completed += 1
            if artifact["error"]:
                failed += 1
                print(
                    f"[FAIL] {artifact['task_id']} attempt {artifact['attempt']}: "
                    f"{artifact['error'][:180]}",
                    flush=True,
                )
            else:
                ok += 1
            if completed % 10 == 0 or completed == total:
                print(
                    f"[cab] progress {completed}/{total} (ok={ok} failed={failed} skipped={skipped})",
                    flush=True,
                )
    result = {
        "run_dir": str(run_dir.resolve()),
        "tasks": len(tasks),
        "attempts": attempts,
        "ok": ok,
        "failed": failed,
        "skipped": skipped,
    }
    return result
