from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import Any

from .config import PipelineConfig


class ProviderError(RuntimeError):
    """A provider call failed permanently."""


class RetryableProviderError(ProviderError):
    """A provider call may succeed if retried."""


@dataclass
class ProviderResponse:
    text: str
    input_tokens: int | None = None
    output_tokens: int | None = None
    response_id: str | None = None


class Provider:
    def __init__(self, config: PipelineConfig):
        self.config = config

    def run(self, prompt: str) -> ProviderResponse:
        raise NotImplementedError


class CommandProvider(Provider):
    def run(self, prompt: str) -> ProviderResponse:
        full_prompt = prompt
        if self.config.system_prompt:
            full_prompt = f"{self.config.system_prompt.rstrip()}\n\n{prompt}"
        # Task prompts contain non-ASCII characters (em dashes, non-breaking spaces).
        # The prompt is written as UTF-8, so the child must decode as UTF-8 too. On
        # Windows a child process otherwise defaults to the console code page and
        # silently corrupts every one of those characters.
        child_env = {**os.environ, "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
        try:
            completed = subprocess.run(
                list(self.config.command),
                input=full_prompt,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=child_env,
                timeout=self.config.timeout_seconds,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise RetryableProviderError(
                f"model command timed out after {self.config.timeout_seconds:g}s"
            ) from exc
        if completed.returncode != 0:
            detail = completed.stderr.strip()[-1000:]
            raise ProviderError(
                f"model command exited with {completed.returncode}: {detail or 'no stderr'}"
            )
        return ProviderResponse(text=completed.stdout)


class OpenAIProvider(Provider):
    def __init__(self, config: PipelineConfig):
        super().__init__(config)
        self._client_instance: Any = None
        self._lock = threading.Lock()

    def _client(self) -> Any:
        if self._client_instance is not None:
            return self._client_instance
        with self._lock:
            if self._client_instance is not None:
                return self._client_instance
            try:
                from openai import OpenAI
            except ImportError as exc:
                raise ProviderError(
                    "OpenAI support is not installed. Run `pip install -e '.[openai]'`."
                ) from exc
            key_name = self.config.api_key_env or "OPENAI_API_KEY"
            api_key = os.environ.get(key_name)
            if not api_key:
                raise ProviderError(f"{key_name} is not set")
            kwargs: dict[str, Any] = {
                "api_key": api_key,
                "timeout": self.config.timeout_seconds,
            }
            if self.config.base_url:
                kwargs["base_url"] = self.config.base_url
            self._client_instance = OpenAI(**kwargs)
            return self._client_instance

    def _messages(self, prompt: str) -> list[dict[str, str]]:
        messages = []
        if self.config.system_prompt:
            messages.append(
                {"role": self.config.system_role, "content": self.config.system_prompt}
            )
        messages.append({"role": "user", "content": prompt})
        return messages

    def run(self, prompt: str) -> ProviderResponse:
        try:
            if self.config.api == "responses":
                kwargs: dict[str, Any] = {
                    "model": self.config.model,
                    "input": self._messages(prompt),
                    "max_output_tokens": self.config.max_tokens,
                }
                if self.config.reasoning_effort:
                    kwargs["reasoning"] = {"effort": self.config.reasoning_effort}
                kwargs.update(self.config.extra_body)
                response = self._client().responses.create(**kwargs)
                usage = getattr(response, "usage", None)
                return ProviderResponse(
                    text=getattr(response, "output_text", "") or "",
                    input_tokens=getattr(usage, "input_tokens", None),
                    output_tokens=getattr(usage, "output_tokens", None),
                    response_id=getattr(response, "id", None),
                )

            kwargs = {
                "model": self.config.model,
                "messages": self._messages(prompt),
                self.config.max_tokens_parameter: self.config.max_tokens,
            }
            if self.config.temperature is not None and not self.config.reasoning_effort:
                kwargs["temperature"] = self.config.temperature
            if self.config.reasoning_effort:
                kwargs["reasoning_effort"] = self.config.reasoning_effort
            if self.config.json_mode:
                kwargs["response_format"] = {"type": "json_object"}
            if self.config.extra_body:
                kwargs["extra_body"] = self.config.extra_body
            response = self._client().chat.completions.create(**kwargs)
            usage = getattr(response, "usage", None)
            return ProviderResponse(
                text=response.choices[0].message.content or "",
                input_tokens=getattr(usage, "prompt_tokens", None),
                output_tokens=getattr(usage, "completion_tokens", None),
                response_id=getattr(response, "id", None),
            )
        except ProviderError:
            raise
        except Exception as exc:
            status = getattr(exc, "status_code", None)
            name = type(exc).__name__.lower()
            if status == 429 or (isinstance(status, int) and status >= 500) or any(
                token in name for token in ("timeout", "ratelimit", "connection")
            ):
                raise RetryableProviderError(f"{type(exc).__name__}: {exc}") from exc
            raise ProviderError(f"{type(exc).__name__}: {exc}") from exc


def create_provider(config: PipelineConfig) -> Provider:
    if config.provider == "command":
        return CommandProvider(config)
    if config.provider in {"openai", "openai_compatible"}:
        return OpenAIProvider(config)
    raise ValueError(f"Unsupported provider: {config.provider}")


def call_with_retries(provider: Provider, prompt: str) -> ProviderResponse:
    delay = provider.config.retry_base_seconds
    for attempt in range(1, provider.config.retries + 1):
        try:
            return provider.run(prompt)
        except RetryableProviderError:
            if attempt == provider.config.retries:
                raise
            time.sleep(delay)
            delay = min(max(delay * 2, 0.1), 60.0)
    raise AssertionError("unreachable")
