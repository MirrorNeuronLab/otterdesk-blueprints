"""Litigation structured-response and audit adapter over SDK model access."""

from contextlib import nullcontext
from dataclasses import dataclass, replace
import json
from typing import Any

from mn_sdk.llm import LLMClient, LLMError, completion_json_result
from rfm_platform.errors import BackendUnavailableError, RFMPlatformError


class LLMResponseError(RFMPlatformError, ValueError):
    request = None
    response = None


@dataclass(frozen=True, slots=True)
class StructuredCompletion:
    value: dict[str, Any]
    content: str
    request: dict[str, Any]
    response: dict[str, Any]
    finish_reason: str
    usage: dict[str, Any]


class SDKInvestigationModel:
    def __init__(self, client=None, context_session=None):
        self.client = client or LLMClient.from_env(strict=True)
        self.model = self.client.model
        self.context_session = context_session

    def complete_json(self, messages, *, temperature=0.1, invocation_id="decision", focus="", required_fields=(), final=False):
        if len(messages) != 2 or [m["role"] for m in messages] != ["system", "user"]:
            raise ValueError("investigation requests require a system/user prompt pair")
        request = {"model": self.model, "messages": list(messages)}
        try:
            if isinstance(self.client, LLMClient):
                # One accounted provider response per decision; the loop owns retries.
                turn = self.context_session.turn(
                    invocation_id, focus=focus, required_fields=required_fields,
                    final=final,
                ) if self.context_session else nullcontext()
                config = replace(self.client.config, num_retries=0)
                if self.context_session:
                    config = replace(config, max_tokens=min(
                        config.max_tokens, self.context_session.policy.output_tokens,
                    ))
                with turn:
                    result = completion_json_result(
                        messages[0]["content"], messages[1]["content"],
                        config=config,
                    )
                content = result.content
                self.client.last_usage = dict(result.usage)
            else:
                # Injected offline test transport implements the same prompt contract.
                content = self.client.completion_text(
                    messages[0]["content"], messages[1]["content"]
                )
        except LLMError as exc:
            if (exc.usage or {}).get("provider_response_count"):
                error = LLMResponseError("model returned invalid JSON object")
                error.request, error.response = (
                    request,
                    {"error": str(exc), "usage": exc.usage},
                )
                raise error from exc
            raise BackendUnavailableError(
                "configured local investigation model failed"
            ) from exc
        usage = dict(getattr(self.client, "last_usage", {}) or {})
        response = {"content": content, "usage": usage}
        try:
            value = json.loads(content)
            if not isinstance(value, dict):
                raise ValueError("response must be a JSON object")
        except (ValueError, TypeError) as exc:
            error = LLMResponseError("model returned invalid JSON object")
            error.request, error.response = request, response
            raise error from exc
        return StructuredCompletion(value, content, request, response, "stop", usage)
