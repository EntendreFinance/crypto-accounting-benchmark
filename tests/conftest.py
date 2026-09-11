from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

EXPECTED = {
    "task_id": "task_0001",
    "asset": "TOK",
    "assetQuantity": "2.5",
    "baseCurrency": "USD",
    "journalEntry": {
        "lines": [
            {
                "ledgerAccountName": "A0001: Wallet",
                "drCr": "Debit",
                "amountBase": "10.00",
                "currency": "USD",
            },
            {
                "ledgerAccountName": "I0001: Income",
                "drCr": "Credit",
                "amountBase": "10.00",
                "currency": "USD",
            },
        ]
    },
    "keyLineAccounts": ["I0001: Income"],
    "rubric": {
        "family": "INCOME_EXPENSE",
        "passThreshold": 0.85,
        "criteria": [
            {"id": "correct_income_expense_treatment", "label": "Treatment", "weight": 0.25},
            {"id": "correct_primary_account", "label": "Primary", "weight": 0.30},
            {"id": "correct_counter_account", "label": "Counter", "weight": 0.15},
            {"id": "correct_drcr", "label": "Dr/Cr", "weight": 0.15},
            {"id": "correct_amount", "label": "Amount", "weight": 0.10},
            {"id": "complete_entry", "label": "Complete", "weight": 0.05},
        ],
    },
}

MODEL_ANSWER = {
    "journalEntry": {"lines": EXPECTED["journalEntry"]["lines"]},
    "assetQuantity": EXPECTED["assetQuantity"],
}


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


@pytest.fixture
def dataset_dir(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    task = root / "tasks" / "task_0001"
    task.mkdir(parents=True)
    (task / "prompt.md").write_text("Return the complete journal entry.\n", encoding="utf-8")
    write_json(
        task / "input.json",
        {
            "task_id": "task_0001",
            "input": {
                "chartOfAccounts": [
                    {"ledgerAccountName": "A0001: Wallet"},
                    {"ledgerAccountName": "I0001: Income"},
                ]
            },
        },
    )
    write_json(task / "expected_answer.json", EXPECTED)
    files = []
    for path in sorted(task.iterdir()):
        relative = path.relative_to(root).as_posix()
        files.append(
            {
                "path": relative,
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    write_json(
        root / "manifest.json",
        {
            "benchmark": "crypto-accounting-bench",
            "license": "test-only",
            "taskCount": 1,
            "taskIds": ["task_0001"],
            "files": files,
        },
    )
    write_json(
        root / ".cab-dataset-source.json",
        {
            "schema": "cab-public-dataset-source",
            "repo_id": "owner/dataset",
            "requested_revision": "main",
            "resolved_revision": "abc123",
        },
    )
    return root
