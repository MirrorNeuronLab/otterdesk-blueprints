"""Research-specific structured LLM request adaptation.

The runtime may expose its automatically selected model through an external
LiteLLM route.  In that case the SDK intentionally preserves the route but
cannot recover catalog-only structured-output options.  This adapter keeps the
configured provider, endpoint, and logical model while applying the
blueprint-declared JSON request options.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Mapping
from typing import Any

from mn_sdk import LLMError, runtime_model_json_request


def _response_content(response: Mapping[str, Any]) -> str:
    message = response.get("message")
    if isinstance(message, Mapping):
        return str(message.get("content") or "")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LLMError("Structured research response omitted choices.")
    first = choices[0] if isinstance(choices[0], Mapping) else {}
    nested = first.get("message") if isinstance(first.get("message"), Mapping) else {}
    return str(nested.get("content") or first.get("text") or "")


def _parse_json_object(content: str) -> dict[str, Any]:
    text = str(content or "").strip()
    if text.startswith("```"):
        lines = text.splitlines()
        if lines and lines[0].strip().lower() in {"```", "```json"}:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    parsed = json.loads(text)
    if not isinstance(parsed, dict):
        raise LLMError("Structured research response was not a JSON object.")
    return parsed


def _usage(response: Mapping[str, Any]) -> dict[str, int]:
    raw = response.get("usage") if isinstance(response.get("usage"), Mapping) else {}
    input_tokens = int(raw.get("prompt_tokens") or raw.get("input_tokens") or 0)
    output_tokens = int(
        raw.get("completion_tokens") or raw.get("output_tokens") or 0
    )
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": int(raw.get("total_tokens") or input_tokens + output_tokens),
    }


class StructuredResearchLlmClient:
    """Apply declared JSON request options without replacing model selection."""

    def __init__(self, base: Any, request_options: Mapping[str, Any]) -> None:
        self._base = base
        self._request_options = copy.deepcopy(dict(request_options))
        self.provider = str(getattr(base, "provider", "docker_model_runner"))
        self.model = str(getattr(base, "model", "default"))
        self.api_base = getattr(base, "api_base", None)
        self.api_key = str(getattr(base, "api_key", "") or "")
        self.backend = str(getattr(base, "backend", "auto") or "auto")
        self.context_size = getattr(base, "context_size", None)
        self.timeout_seconds = float(getattr(base, "timeout_seconds", 60.0) or 60.0)
        self.max_tokens = int(getattr(base, "max_tokens", 800) or 800)
        self.num_retries = max(int(getattr(base, "num_retries", 0) or 0), 0)
        self.retry_backoff_seconds = max(
            float(getattr(base, "retry_backoff_seconds", 1.0) or 0.0), 0.0
        )
        self.strict = bool(getattr(base, "strict", False))
        self.calls = 0
        self.fallback_calls = 0
        self.input_tokens = 0
        self.output_tokens = 0
        self.total_tokens = 0
        self.estimated_tokens = 0
        self.last_usage: dict[str, Any] = {}

    def __getattr__(self, name: str) -> Any:
        return getattr(self._base, name)

    def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        fallback: dict[str, Any],
        validator: Any | None = None,
        validation_retries: int = 0,
    ) -> dict[str, Any]:
        del validation_retries
        self.calls += 1
        responses = 0
        usages: list[dict[str, int]] = []
        error: Exception | None = None
        for attempt in range(self.num_retries + 1):
            retry_note = (
                "\nA previous response was invalid. Return one complete JSON object now."
                if attempt
                else ""
            )
            payload: dict[str, Any] = {
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"{system_prompt}\nReturn only one valid JSON object."
                            f"{retry_note}"
                        ),
                    },
                    {"role": "user", "content": user_prompt},
                ],
                "max_tokens": self.max_tokens,
                "response_format": {"type": "json_object"},
                **copy.deepcopy(self._request_options),
            }
            try:
                response = runtime_model_json_request(
                    "llm",
                    self.model,
                    "/chat/completions",
                    payload,
                    provider=self.provider,
                    backend=self.backend,
                    context_size=self.context_size,
                    api_base=self.api_base,
                    api_key=self.api_key,
                    timeout_seconds=self.timeout_seconds,
                    num_retries=0,
                    retry_backoff_seconds=self.retry_backoff_seconds,
                )
                responses += 1
                usages.append(_usage(response))
                parsed = _parse_json_object(_response_content(response))
                if validator is not None:
                    validated = validator(parsed)
                    if not isinstance(validated, Mapping):
                        raise LLMError(
                            "Structured research response did not match its contract."
                        )
                    parsed = dict(validated)
                self._record_usage(usages, provider_response_count=responses)
                parsed.setdefault("provider", self.provider)
                parsed.setdefault("model", self.model)
                return parsed
            except Exception as exc:  # provider and parse failures share retry policy
                error = exc

        self.fallback_calls += 1
        self._record_usage(
            usages,
            provider_response_count=responses,
            fallback=True,
            fallback_reason=(
                "invalid_structured_output" if responses else "provider_request_failed"
            ),
        )
        if self.strict:
            if isinstance(error, LLMError):
                raise error
            raise LLMError(f"Structured research request failed: {error}") from error
        result = dict(fallback)
        result.setdefault("provider", self.provider if responses else "llm_unavailable")
        result.setdefault("model", self.model)
        return result

    def _record_usage(
        self,
        usages: list[dict[str, int]],
        *,
        provider_response_count: int,
        fallback: bool = False,
        fallback_reason: str = "",
    ) -> None:
        combined = {
            "input_tokens": sum(item["input_tokens"] for item in usages),
            "output_tokens": sum(item["output_tokens"] for item in usages),
            "total_tokens": sum(item["total_tokens"] for item in usages),
            "estimated": False,
            "provider": self.provider,
            "model": self.model,
            "source": "provider" if provider_response_count == 1 else "provider_structured_retry",
            "provider_response_count": provider_response_count,
        }
        if fallback:
            combined["fallback"] = True
            combined["fallback_reason"] = fallback_reason
        self.last_usage = combined
        self.input_tokens += combined["input_tokens"]
        self.output_tokens += combined["output_tokens"]
        self.total_tokens += combined["total_tokens"]


def adapt_structured_research_llm(base: Any, config: Mapping[str, Any]) -> Any:
    llm_config = config.get("llm") if isinstance(config.get("llm"), Mapping) else {}
    options = llm_config.get("structured_output_options")
    provider = str(getattr(base, "provider", "")).lower()
    if (
        not isinstance(options, Mapping)
        or not options
        or provider in {"fake", "deterministic", "mock"}
    ):
        return base
    return StructuredResearchLlmClient(base, options)


__all__ = ["StructuredResearchLlmClient", "adapt_structured_research_llm"]
