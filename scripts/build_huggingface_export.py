from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def _file_row(root: Path, path: Path) -> dict[str, Any]:
    payload = path.read_bytes()
    return {
        "path": path.relative_to(root).as_posix(),
        "bytes": len(payload),
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def build_export(root: Path) -> tuple[Path, int]:
    root = root.resolve()
    manifest_path = root / "manifest.json"
    manifest = _load_json(manifest_path)
    expected_ids = [str(value) for value in manifest.get("taskIds", [])]
    if not expected_ids:
        raise ValueError("manifest taskIds must be populated")

    output = root / "data" / "tasks.jsonl"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8", newline="\n") as stream:
        for task_id in expected_ids:
            task_dir = root / "tasks" / task_id
            row = {
                "task_id": task_id,
                "prompt": (task_dir / "prompt.md").read_text(encoding="utf-8"),
                "input": _load_json(task_dir / "input.json"),
                "expected_answer": _load_json(task_dir / "expected_answer.json"),
            }
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")))
            stream.write("\n")

    excluded_roots = {".cache", ".git"}
    excluded_files = {
        ".gitattributes",
        "manifest.json",
        ".cab-dataset-source.json",
        "mirror-selftest.json",
    }
    files = [
        path
        for path in root.rglob("*")
        if path.is_file()
        and not any(part in excluded_roots for part in path.relative_to(root).parts)
        and path.relative_to(root).as_posix() not in excluded_files
        and not path.name.startswith("mirror-selftest")
    ]
    manifest["files"] = [_file_row(root, path) for path in sorted(files)]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return output, len(expected_ids)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build the Hugging Face Viewer JSONL projection and refresh manifest hashes."
    )
    parser.add_argument("dataset_root", type=Path)
    args = parser.parse_args()
    output, rows = build_export(args.dataset_root)
    print(json.dumps({"output": str(output), "rows": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
