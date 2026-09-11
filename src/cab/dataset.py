from __future__ import annotations

import hashlib
import os
from decimal import Decimal
from pathlib import Path
from typing import Any

from .utils import atomic_write_json, load_json, sha256_file, utc_now

DEFAULT_DATASET_REPO = "Entendre/Crypto-Accounting-Bench"
REQUIRED_TASK_FILES = ("prompt.md", "input.json", "expected_answer.json")
SOURCE_METADATA_FILE = ".cab-dataset-source.json"


def task_directories(data_dir: str | Path) -> list[Path]:
    root = Path(data_dir) / "tasks"
    if not root.is_dir():
        raise FileNotFoundError(
            f"Dataset not found at {root}. Run `cab dataset download` first."
        )
    return sorted(path for path in root.glob("task_*") if path.is_dir())


def dataset_digest(data_dir: str | Path) -> str:
    digest = hashlib.sha256()
    root = Path(data_dir)
    for task_dir in task_directories(root):
        for name in REQUIRED_TASK_FILES:
            path = task_dir / name
            relative = path.relative_to(root).as_posix().encode("utf-8")
            digest.update(len(relative).to_bytes(4, "big"))
            digest.update(relative)
            digest.update(path.read_bytes())
    return digest.hexdigest()


def _windows_path_limit_hit(destination: Path, exc: BaseException) -> bool:
    """A download path past the Windows limit surfaces as a bare FileNotFoundError."""
    if os.name != "nt" or not isinstance(exc, FileNotFoundError):
        return False
    return len(str(destination)) > 120 or ".incomplete" in str(exc)


def download_dataset(
    data_dir: str | Path = "data",
    repo_id: str = DEFAULT_DATASET_REPO,
    revision: str = "main",
) -> Path:
    try:
        from huggingface_hub import HfApi, snapshot_download
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install the project first: `pip install -e .`") from exc
    destination = Path(data_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    try:
        snapshot_download(
            repo_id=repo_id,
            repo_type="dataset",
            revision=revision,
            local_dir=destination,
        )
    except OSError as exc:
        if _windows_path_limit_hit(destination, exc):
            raise RuntimeError(
                "The download exceeded the Windows 260-character path limit under "
                f"{destination}. Clone the repository closer to the drive root "
                "(for example C:\\cab), or pass a shorter --data-dir."
            ) from exc
        raise
    resolved_revision = HfApi().dataset_info(repo_id, revision=revision).sha
    atomic_write_json(
        destination / SOURCE_METADATA_FILE,
        {
            "schema": "cab-public-dataset-source",
            "repo_id": repo_id,
            "requested_revision": revision,
            "resolved_revision": resolved_revision,
            "downloaded_at": utc_now(),
        },
    )
    return destination


def verify_dataset(data_dir: str | Path = "data") -> dict[str, Any]:
    root = Path(data_dir)
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Missing dataset manifest: {manifest_path}")
    manifest = load_json(manifest_path)
    tasks = task_directories(root)
    actual_ids = [path.name for path in tasks]
    errors: list[str] = []
    expected_count = int(manifest.get("taskCount", 0))
    raw_expected_ids = manifest.get("taskIds")
    expected_ids = [str(value) for value in raw_expected_ids] if isinstance(raw_expected_ids, list) else []
    if not expected_ids:
        errors.append("manifest taskIds must be a non-empty list")
    if len(expected_ids) != len(set(expected_ids)):
        errors.append("manifest taskIds contains duplicates")
    if len(expected_ids) != expected_count:
        errors.append(
            f"manifest taskIds contains {len(expected_ids)} ids; taskCount says {expected_count}"
        )
    if len(tasks) != expected_count:
        errors.append(f"task count is {len(tasks)}; manifest says {expected_count}")
    missing_ids = sorted(set(expected_ids) - set(actual_ids))
    unexpected_ids = sorted(set(actual_ids) - set(expected_ids))
    if missing_ids:
        errors.append(f"missing task directories: {', '.join(missing_ids[:10])}")
    if unexpected_ids:
        errors.append(f"unexpected task directories: {', '.join(unexpected_ids[:10])}")

    manifest_files: dict[str, str] = {}
    for row in manifest.get("files", []):
        relative = str(row.get("path", ""))
        if not relative.startswith("tasks/"):
            continue
        if relative in manifest_files:
            errors.append(f"duplicate manifest file entry: {relative}")
        manifest_files[relative] = str(row.get("sha256", ""))
    checked_hashes = 0
    for task_id in expected_ids:
        task_dir = root / "tasks" / task_id
        for name in REQUIRED_TASK_FILES:
            path = task_dir / name
            relative = path.relative_to(root).as_posix()
            expected_hash = manifest_files.get(relative)
            if not expected_hash:
                errors.append(f"missing manifest checksum: {relative}")
            if not path.is_file():
                errors.append(f"missing {relative}")
                continue
            if expected_hash:
                checked_hashes += 1
                if sha256_file(path) != expected_hash:
                    errors.append(f"checksum mismatch: {relative}")
        if any(not (task_dir / name).is_file() for name in REQUIRED_TASK_FILES):
            continue
        task_input = load_json(task_dir / "input.json")
        expected = load_json(task_dir / "expected_answer.json")
        criteria = expected.get("rubric", {}).get("criteria", [])
        weight = sum(Decimal(str(row.get("weight", 0))) for row in criteria)
        if weight != Decimal(1):
            errors.append(f"{task_dir.name}: rubric weights sum to {weight}")
        chart = {
            str(row.get("ledgerAccountName"))
            for row in task_input.get("input", {}).get("chartOfAccounts", [])
        }
        answer_accounts = {
            str(row.get("ledgerAccountName"))
            for row in expected.get("journalEntry", {}).get("lines", [])
        }
        missing_accounts = sorted(answer_accounts - chart)
        if missing_accounts:
            errors.append(f"{task_dir.name}: answer accounts missing from chart: {missing_accounts}")

    source_path = root / SOURCE_METADATA_FILE
    source = load_json(source_path) if source_path.is_file() else {}
    try:
        digest = dataset_digest(root)
    except OSError as exc:
        errors.append(f"cannot compute dataset digest: {exc}")
        digest = None
    result = {
        "ok": not errors,
        "benchmark": manifest.get("benchmark"),
        "license": manifest.get("license"),
        "tasks": len(tasks),
        "task_file_hashes_checked": checked_hashes,
        "dataset_sha256": digest,
        "repo_id": source.get("repo_id"),
        "requested_revision": source.get("requested_revision"),
        "resolved_revision": source.get("resolved_revision"),
        "errors": errors,
    }
    if errors:
        raise ValueError("Dataset verification failed:\n- " + "\n- ".join(errors[:25]))
    return result
