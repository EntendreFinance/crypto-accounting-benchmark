from __future__ import annotations

from pathlib import Path

from cab.config import load_pipeline


def test_load_command_pipeline_and_system_prompt(tmp_path: Path) -> None:
    (tmp_path / "system.md").write_text("Return JSON.", encoding="utf-8")
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        """name: local
provider: command
model: fixture
system_prompt: system.md
command: [python, model.py]
""",
        encoding="utf-8",
    )
    config = load_pipeline(pipeline)
    assert config.name == "local"
    assert config.command == ("python", "model.py")
    assert config.system_prompt == "Return JSON."
    assert len(config.public_dict()["system_prompt_sha256"]) == 64


def test_pipeline_identity_changes_with_effective_request_config(tmp_path: Path) -> None:
    (tmp_path / "system.md").write_text("First prompt.", encoding="utf-8")
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        """name: model
provider: openai
model: model-id
system_prompt: system.md
extra_body:
  seed: 7
""",
        encoding="utf-8",
    )
    first = load_pipeline(pipeline).public_dict()
    (tmp_path / "system.md").write_text("Second prompt.", encoding="utf-8")
    second = load_pipeline(pipeline).public_dict()
    assert first["system_prompt_sha256"] != second["system_prompt_sha256"]
    assert first["extra_body"] == {"seed": 7}


def test_openai_pipeline_never_contains_key_value(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        "name: model\nprovider: openai\nmodel: model-id\napi_key_env: SECRET_ENV\n",
        encoding="utf-8",
    )
    public = load_pipeline(pipeline).public_dict()
    assert public["api_key_env"] == "SECRET_ENV"
    assert "api_key" not in public
