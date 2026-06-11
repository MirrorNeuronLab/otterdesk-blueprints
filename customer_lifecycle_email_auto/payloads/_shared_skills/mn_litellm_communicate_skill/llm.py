from __future__ import annotations

import contextlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

try:
    from mn_external_rate_limit_skill import call_with_rate_limit
except ImportError:  # pragma: no cover - optional sibling skill
    def call_with_rate_limit(key, func, *args, rate_limit_min_interval_seconds=None, **kwargs):
        return func(*args, **kwargs)


class LLMError(RuntimeError):
    pass


@dataclass(frozen=True)
class LLMConfig:
    model: str
    api_base: str | None
    api_key: str
    timeout_seconds: float
    max_tokens: int
    num_retries: int
    retry_backoff_seconds: float


def resolve_config() -> LLMConfig:
    model = os.environ.get("LITELLM_MODEL", "ollama/nemotron3:33b").strip()
    api_base = os.environ.get("LITELLM_API_BASE", "").strip() or None
    if model.startswith("ollama/") and api_base is None:
        api_base = "http://192.168.4.173:11434"

    return LLMConfig(
        model=model,
        api_base=_normalize_api_base(api_base),
        api_key=os.environ.get("LITELLM_API_KEY", "").strip(),
        timeout_seconds=float(os.environ.get("LITELLM_TIMEOUT_SECONDS", "3")),
        max_tokens=int(os.environ.get("LITELLM_MAX_TOKENS", "800")),
        num_retries=max(int(os.environ.get("LITELLM_NUM_RETRIES", "0")), 0),
        retry_backoff_seconds=max(float(os.environ.get("LITELLM_RETRY_BACKOFF_SECONDS", "1.0")), 0.0),
    )


def completion_text(
    system_prompt: str,
    user_prompt: str,
    *,
    fallback: str | None = None,
    config: LLMConfig | None = None,
) -> str:
    config = config or resolve_config()
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    try:
        return _completion_with_litellm(messages, config)
    except ImportError:
        pass
    except Exception as exc:
        if fallback is not None:
            return fallback
        raise LLMError(f"LiteLLM request failed: {exc}") from exc

    try:
        if config.model.startswith("ollama/"):
            return _completion_with_ollama(messages, config)
        return _completion_with_openai_compatible(messages, config)
    except Exception as exc:
        if fallback is not None:
            return fallback
        raise LLMError(f"LLM request failed: {exc}") from exc


def completion_json(
    system_prompt: str,
    user_prompt: str,
    *,
    fallback: dict[str, Any] | None = None,
    config: LLMConfig | None = None,
) -> dict[str, Any] | None:
    fallback_text = json.dumps(fallback) if fallback is not None else None
    text = completion_text(system_prompt, user_prompt, fallback=fallback_text, config=config)
    try:
        return _parse_json_object(text)
    except Exception as exc:
        if fallback is not None:
            return fallback
        raise LLMError(f"LLM did not return valid JSON: {exc}") from exc


def _completion_with_litellm(messages: list[dict[str, str]], config: LLMConfig) -> str:
    import litellm
    from litellm import completion

    request_kwargs: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "max_tokens": config.max_tokens,
        "timeout": config.timeout_seconds,
        "num_retries": config.num_retries,
    }
    if config.api_key:
        request_kwargs["api_key"] = config.api_key
    if config.api_base:
        request_kwargs["api_base"] = config.api_base

    try:
        supported = set(litellm.get_supported_openai_params(model=config.model) or [])
    except Exception:
        supported = set()

    if "response_format" in supported:
        request_kwargs["response_format"] = {"type": "json_object"}
    if config.model.startswith("ollama/"):
        request_kwargs["format"] = "json"

    with contextlib.redirect_stdout(sys.stderr):
        response = call_with_rate_limit(
            f"llm.{config.model}",
            completion,
            rate_limit_min_interval_seconds=1.0,
            **request_kwargs,
        )

    return response.choices[0].message.content or ""


def _completion_with_ollama(messages: list[dict[str, str]], config: LLMConfig) -> str:
    if not config.api_base:
        raise LLMError("LITELLM_API_BASE is required for Ollama fallback")

    model = config.model.removeprefix("ollama/")
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {"num_predict": config.max_tokens},
    }
    response = _post_json_with_retry(f"{config.api_base}/api/chat", payload, config)
    message = response.get("message") or {}
    return str(message.get("content", ""))


def _completion_with_openai_compatible(messages: list[dict[str, str]], config: LLMConfig) -> str:
    if not config.api_base:
        raise LLMError("LITELLM_API_BASE is required without the litellm package")

    payload = {
        "model": config.model,
        "messages": messages,
        "max_tokens": config.max_tokens,
    }
    response = _post_json_with_retry(f"{config.api_base}/chat/completions", payload, config)
    return str(response["choices"][0]["message"]["content"])


def _post_json_with_retry(url: str, payload: dict[str, Any], config: LLMConfig) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(config.num_retries + 1):
        try:
            return _post_json(url, payload, config)
        except Exception as exc:
            last_error = exc
            if attempt >= config.num_retries:
                break
            if config.retry_backoff_seconds > 0:
                time.sleep(config.retry_backoff_seconds * (2**attempt))
    raise LLMError(f"LLM request failed after {config.num_retries + 1} attempts: {last_error}") from last_error


def _post_json(url: str, payload: dict[str, Any], config: LLMConfig) -> dict[str, Any]:
    headers = {"Content-Type": "application/json"}
    if config.api_key:
        headers["Authorization"] = f"Bearer {config.api_key}"

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    try:
        with call_with_rate_limit(
            f"llm.{config.model}",
            urllib.request.urlopen,
            request,
            timeout=config.timeout_seconds,
            rate_limit_min_interval_seconds=1.0,
        ) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LLMError(f"HTTP {exc.code} from {url}: {body}") from exc


def _normalize_api_base(api_base: str | None) -> str | None:
    if not api_base:
        return None
    value = api_base.rstrip("/")
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1"):
        if value.endswith(suffix):
            value = value[: -len(suffix)]
    return value.rstrip("/") or None


def _parse_json_object(text: str) -> dict[str, Any]:
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            raise
        value = json.loads(text[start : end + 1])

    if not isinstance(value, dict):
        raise LLMError("expected JSON object")
    return value
