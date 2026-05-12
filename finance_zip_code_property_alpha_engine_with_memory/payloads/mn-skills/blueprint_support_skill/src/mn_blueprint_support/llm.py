from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


DEFAULT_OLLAMA_BASE = "http://192.168.4.173:11434"
DEFAULT_MODEL = "ollama/nemotron3:33b"


class LLMClient(Protocol):
    provider: str
    model: str
    calls: int

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        ...


class FakeLLMClient:
    """Deterministic LLM stand-in used by fast blueprint tests."""

    provider = "fake"
    model = "fake-deterministic-blueprint-agent"

    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response.setdefault("confidence", 0.78)
        response["rationale"] = (
            response.get("rationale")
            or "Deterministic fake agent selected the strongest simulated action."
        )
        response["provider"] = self.provider
        return response


@dataclass
class OllamaLLMClient:
    """Small Ollama adapter with optional reuse of the local LiteLLM skill."""

    model: str = DEFAULT_MODEL
    api_base: str = DEFAULT_OLLAMA_BASE
    timeout_seconds: float = 60.0
    max_tokens: int = 700
    num_retries: int = 1
    retry_backoff_seconds: float = 1.0
    strict: bool = False
    prefer_shared_skill: bool = True

    provider: str = "ollama"
    calls: int = 0
    fallback_calls: int = 0

    @classmethod
    def from_env(cls, *, strict: bool = False, prefer_shared_skill: bool = True) -> "OllamaLLMClient":
        model = _env("MN_LLM_MODEL", "LITELLM_MODEL", default=DEFAULT_MODEL).strip() or DEFAULT_MODEL
        if not model.startswith("ollama/"):
            model = f"ollama/{model}"
        return cls(
            model=model,
            api_base=(_env("MN_LLM_API_BASE", "LITELLM_API_BASE", default=DEFAULT_OLLAMA_BASE).strip() or DEFAULT_OLLAMA_BASE).rstrip("/"),
            timeout_seconds=float(_env("MN_LLM_TIMEOUT_SECONDS", "LITELLM_TIMEOUT_SECONDS", default="60")),
            max_tokens=int(_env("MN_LLM_MAX_TOKENS", "LITELLM_MAX_TOKENS", default="700")),
            num_retries=max(int(_env("MN_LLM_NUM_RETRIES", "LITELLM_NUM_RETRIES", default="1")), 0),
            retry_backoff_seconds=max(float(_env("MN_LLM_RETRY_BACKOFF_SECONDS", "LITELLM_RETRY_BACKOFF_SECONDS", default="1.0")), 0.0),
            strict=strict,
            prefer_shared_skill=prefer_shared_skill,
        )

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
    ) -> dict[str, Any]:
        self.calls += 1
        last_error: Exception | None = None
        for attempt in range(self.num_retries + 1):
            try:
                if not self.prefer_shared_skill:
                    raise ImportError("shared skill disabled for this call")
                response = self._generate_with_skill(system_prompt, user_prompt, fallback)
            except Exception:
                response = self._generate_direct(system_prompt, user_prompt)

            try:
                parsed = _parse_json_object(response)
                break
            except Exception as exc:
                last_error = exc
                if attempt < self.num_retries and self.retry_backoff_seconds:
                    time.sleep(self.retry_backoff_seconds * (2**attempt))
        else:
            if self.strict and last_error is not None:
                raise last_error
            self.fallback_calls += 1
            parsed = dict(fallback)

        parsed.setdefault("provider", self.provider)
        parsed.setdefault("model", self.model)
        return parsed

    def _generate_with_skill(self, system_prompt: str, user_prompt: str, fallback: dict[str, Any]) -> str:
        skill_path_added = False
        for parent in Path(__file__).resolve().parents:
            candidates = [
                parent / "litellm_communicate_skill" / "src",
                parent / "mn-skills" / "litellm_communicate_skill" / "src",
            ]
            for skill_src in candidates:
                if skill_src.exists() and str(skill_src) not in sys.path:
                    sys.path.insert(0, str(skill_src))
                    skill_path_added = True
                    break
            if skill_path_added:
                break

        from mn_litellm_communicate_skill import LLMConfig, completion_json

        data = completion_json(
            system_prompt,
            user_prompt,
            fallback=fallback,
            config=LLMConfig(
                model=self.model,
                api_base=self.api_base,
                api_key=_env("MN_LLM_API_KEY", "LITELLM_API_KEY", default="").strip(),
                timeout_seconds=self.timeout_seconds,
                max_tokens=self.max_tokens,
                num_retries=self.num_retries,
                retry_backoff_seconds=self.retry_backoff_seconds,
            ),
        )
        return json.dumps(data or fallback)

    def _generate_direct(self, system_prompt: str, user_prompt: str) -> str:
        model = self.model.removeprefix("ollama/")
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{system_prompt}\nReturn only valid JSON with keys: "
                        "action, confidence, rationale, parameters."
                    ),
                },
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"num_predict": self.max_tokens, "temperature": 0.1},
        }
        response = self._post_json(f"{self.api_base}/api/chat", payload)
        message = response.get("message") or {}
        return str(message.get("content", ""))

    def _post_json(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.num_retries + 1):
            try:
                request = urllib.request.Request(
                    url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    return json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                last_error = RuntimeError(exc.read().decode("utf-8", errors="replace"))
            except Exception as exc:
                last_error = exc
            if attempt < self.num_retries and self.retry_backoff_seconds:
                time.sleep(self.retry_backoff_seconds * (2**attempt))
        raise RuntimeError(f"Ollama request failed: {last_error}") from last_error


def get_llm_client(mode: str | None = None) -> LLMClient:
    selected = (mode or os.getenv("MN_BLUEPRINT_LLM_MODE", "ollama")).strip().lower()
    if selected in {"fake", "mock", "deterministic"}:
        return FakeLLMClient()
    if selected in {"ollama", "live", "real"}:
        return OllamaLLMClient.from_env()
    raise ValueError(f"unknown LLM mode {selected!r}; expected fake or ollama")


def _env(primary: str, legacy: str, *, default: str) -> str:
    value = os.environ.get(primary)
    if value is not None:
        return value
    return os.environ.get(legacy, default)


def ollama_model_available(api_base: str = DEFAULT_OLLAMA_BASE, model: str = "nemotron3:33b", timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"{api_base.rstrip('/')}/api/tags", timeout=timeout) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception:
        return False
    return any(item.get("name") == model for item in data.get("models", []))


def _parse_json_object(text: str) -> dict[str, Any]:
    if isinstance(text, dict):
        return text
    cleaned = str(text).strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```[a-zA-Z0-9_-]*\n?", "", cleaned)
        cleaned = re.sub(r"\n?```$", "", cleaned).strip()
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(cleaned[start : end + 1])
    if not isinstance(value, dict):
        raise ValueError("LLM response must be a JSON object")
    return value
