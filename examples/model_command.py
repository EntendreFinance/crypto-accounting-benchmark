"""Template for the `command` provider.

The runner writes the system prompt and the task prompt to this program's stdin as
UTF-8, and reads one answer JSON object from stdout. Replace `answer_for` with your
model call.

The runner sets PYTHONIOENCODING=utf-8 for this process, so `sys.stdin.read()` is
safe. If you write an adapter in another language, decode stdin as UTF-8 explicitly:
task prompts contain em dashes and non-breaking spaces, and a locale default such as
Windows cp1252 corrupts them silently.

As shipped this returns an empty entry, which scores zero while proving the wiring
works end to end. Run it with:

    cab run --pipeline pipelines/local-command.example.yaml --attempts 1 --limit 3
"""
from __future__ import annotations

import json
import sys


def answer_for(prompt: str) -> dict:
    """Return the journal entry your model produces for this prompt."""
    return {
        "assetQuantity": "",
        "journalEntry": {"lines": []},
    }


def main() -> int:
    prompt = sys.stdin.read()
    json.dump(answer_for(prompt), sys.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
