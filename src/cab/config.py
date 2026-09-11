from __future__ import annotations

import hashlib
import json
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

SUPPORTED_PROVIDERS = {"openai", "openai_compatible", "command"}


@dataclass(frozen=True)
class PipelineConfig:
    name: str
    provider: str
    model: str
    api_key_env: str | None = None
    base_url: str | None = None
    api: str = "chat_completions"
    system_prompt: str = ""
    system_role: str = "system"
    max_tokens: int = 4096
    max_tokens_parameter: str = "max_completion_tokens"
    temperature: float | None = 0.0
    reasoning_effort: str | None = None
    timeout_seconds: float = 600.0
    retries: int = 4
    retry_base_seconds: float = 2.0
    json_mode: bool = True
    command: tuple[str, ...] = ()
    extra_body: dict[str, Any] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        system_prompt_sha256 = hashlib.sha256(self.system_prompt.encode("utf-8")).hexdigest()
        return {
            "name": self.name,
            "provider": self.provider,
            "model": self.model,
            "api": self.api,
            "base_url": self.base_url,
            "api_key_env": self.api_key_env,
            "system_role": self.system_role,
            "system_prompt_sha256": system_prompt_sha256,
            "max_tokens": self.max_tokens,
            "max_tokens_parameter": self.max_tokens_parameter,
            "temperature": self.temperature,
            "reasoning_effort": self.reasoning_effort,
            "timeout_seconds": self.timeout_seconds,
            "retries": self.retries,
            "retry_base_seconds": self.retry_base_seconds,
            "json_mode": self.json_mode,
            "command": list(self.command),
            "extra_body": json.loads(json.dumps(self.extra_body, sort_keys=True)),
        }


def _resolve_text(value: str | None, pipeline_path: Path) -> str:
    if not value:
        return ""
    candidate = Path(value)
    if candidate.is_absolute():
        return candidate.read_text(encoding="utf-8")
    for root in (pipeline_path.parent, Path.cwd(), pipeline_path.parent.parent):
        path = root / candidate
        if path.is_file():
            return path.read_text(encoding="utf-8")
    return value


def load_pipeline(path: str | Path) -> PipelineConfig:
    pipeline_path = Path(path).resolve()
    raw = yaml.safe_load(pipeline_path.read_text(encoding="utf-8")) or {}
    provider = str(raw.get("provider", "")).strip().lower().replace("-", "_")
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError(
            f"Unsupported provider {provider!r}. Choose one of: {', '.join(sorted(SUPPORTED_PROVIDERS))}."
        )
    name = str(raw.get("name") or pipeline_path.stem).strip()
    model = str(raw.get("model") or name).strip()
    command_value = raw.get("command") or []
    if isinstance(command_value, str):
        command = tuple(shlex.split(command_value, posix=True))
    elif isinstance(command_value, list):
        command = tuple(str(part) for part in command_value)
    else:
        raise TypeError("pipeline command must be a string or a list")
    if provider == "command" and not command:
        raise ValueError("command pipelines require a non-empty command")
    return PipelineConfig(
        name=name,
        provider=provider,
        model=model,
        api_key_env=(str(raw["api_key_env"]) if raw.get("api_key_env") else None),
        base_url=(str(raw["base_url"]) if raw.get("base_url") else None),
        api=str(raw.get("api", "chat_completions")),
        system_prompt=_resolve_text(raw.get("system_prompt"), pipeline_path),
        system_role=str(raw.get("system_role", "system")),
        max_tokens=int(raw.get("max_tokens", 4096)),
        max_tokens_parameter=str(raw.get("max_tokens_parameter", "max_completion_tokens")),
        temperature=(None if raw.get("temperature") is None else float(raw.get("temperature", 0.0))),
        reasoning_effort=(str(raw["reasoning_effort"]) if raw.get("reasoning_effort") else None),
        timeout_seconds=float(raw.get("timeout_seconds", 600)),
        retries=max(1, int(raw.get("retries", 4))),
        retry_base_seconds=max(0.0, float(raw.get("retry_base_seconds", 2))),
        json_mode=bool(raw.get("json_mode", True)),
        command=command,
        extra_body=dict(raw.get("extra_body") or {}),
    )


def discover_pipelines(directory: str | Path = "pipelines") -> list[tuple[Path, PipelineConfig | Exception]]:
    rows: list[tuple[Path, PipelineConfig | Exception]] = []
    for path in sorted(Path(directory).glob("*.yaml")):
        try:
            rows.append((path, load_pipeline(path)))
        except Exception as exc:  # noqa: BLE001 - list every broken configuration
            rows.append((path, exc))
    return rows
