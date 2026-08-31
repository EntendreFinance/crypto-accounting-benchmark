from __future__ import annotations

import json
import sys
from pathlib import Path

from cab.config import PipelineConfig
from cab.providers import create_provider

# An em dash, a non-breaking space and a currency sign: all present in real task
# prompts, and all corrupted if the adapter decodes stdin with a locale code page.
NON_ASCII_PROMPT = "Fee — 1 234,56 € paid on settlement.\n"


def _echo_adapter(tmp_path: Path) -> Path:
    """An adapter that reads stdin the obvious way, with no encoding of its own."""
    script = tmp_path / "echo_prompt.py"
    script.write_text(
        "import json, sys\n"
        "json.dump({'received': sys.stdin.read()}, sys.stdout)\n",
        encoding="utf-8",
    )
    return script


def test_command_adapter_receives_the_prompt_unchanged(tmp_path: Path) -> None:
    config = PipelineConfig(
        name="echo",
        provider="command",
        model="echo",
        command=(sys.executable, str(_echo_adapter(tmp_path))),
        retries=1,
    )

    response = create_provider(config).run(NON_ASCII_PROMPT)

    assert json.loads(response.text)["received"] == NON_ASCII_PROMPT


def test_command_adapter_receives_the_system_prompt_first(tmp_path: Path) -> None:
    config = PipelineConfig(
        name="echo",
        provider="command",
        model="echo",
        command=(sys.executable, str(_echo_adapter(tmp_path))),
        system_prompt="You are an accountant — answer in JSON.",
        retries=1,
    )

    received = json.loads(create_provider(config).run(NON_ASCII_PROMPT).text)["received"]

    assert received == "You are an accountant — answer in JSON.\n\n" + NON_ASCII_PROMPT
