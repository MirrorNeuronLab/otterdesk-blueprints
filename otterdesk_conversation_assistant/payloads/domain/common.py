"""Identity, runtime bootstrap, and bounded helpers."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any


BLUEPRINT_ID = "otterdesk_conversation_assistant"
BLUEPRINT_NAME = "OtterDesk Conversation Assistant"
REQUEST_SCHEMA = "otterdesk.conversation_assistant.request.v2"
CONTEXT_SCHEMA = "otterdesk.worker_stable_job_mcp_context.v1"
SUPERVISION_SCHEMA = "otterdesk.worker_supervision_context.v1"
OUTPUT_SCHEMA = "otterdesk.conversation_assistant.reply.v1"
OUTPUT_TYPE = "otterdesk_conversation_reply"
PREPARED_CONTEXT_PATH = "workflow_state/conversation_context.json"
MAX_QUESTION_LENGTH = 20_000
MAX_CONTEXT_BYTES = 512 * 1024
MAX_SUPERVISION_CONTEXT_BYTES = 64 * 1024
MAX_RECORDS = 50
MAX_PROMPT_RECORDS = 12
RUNTIME_SKILL_PACKAGES = ("mirrorneuron-blueprint-support-skill",)


def _bootstrap_runtime() -> None:
    for parent in Path(__file__).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if not helper.exists():
            continue
        spec = importlib.util.spec_from_file_location("otterdesk_blueprint_env", helper)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.bootstrap_blueprint_runtime(__file__, packages=RUNTIME_SKILL_PACKAGES)
        return


_bootstrap_runtime()

from mn_blueprint_support import DeterministicFallbackLLM, get_actor_llm_client


class QuickTestConversationLLM(DeterministicFallbackLLM):
    def __init__(self) -> None:
        super().__init__(
            "deterministic-otterdesk-conversation",
            default_summary="The latest read-only MCP snapshot was reviewed.",
            confidence=0.7,
        )


def as_record(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def compact_text(value: Any, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]


def encoded_size(value: Any) -> int:
    return len(json.dumps(value, sort_keys=True, default=str).encode("utf-8"))


def quick_test_enabled(config: dict[str, Any]) -> bool:
    execution = as_record(config.get("execution"))
    llm = as_record(config.get("llm"))
    return bool(execution.get("quick_test")) or str(llm.get("mode") or "").lower() in {
        "fake",
        "mock",
        "test",
    }


def conversation_llm(config: dict[str, Any], provided: Any | None = None) -> Any:
    if provided is not None:
        return provided
    if quick_test_enabled(config):
        return QuickTestConversationLLM()
    return get_actor_llm_client(config, None)


__all__ = [
    "BLUEPRINT_ID",
    "BLUEPRINT_NAME",
    "CONTEXT_SCHEMA",
    "SUPERVISION_SCHEMA",
    "MAX_CONTEXT_BYTES",
    "MAX_SUPERVISION_CONTEXT_BYTES",
    "MAX_QUESTION_LENGTH",
    "MAX_RECORDS",
    "MAX_PROMPT_RECORDS",
    "OUTPUT_SCHEMA",
    "OUTPUT_TYPE",
    "PREPARED_CONTEXT_PATH",
    "REQUEST_SCHEMA",
    "as_record",
    "compact_text",
    "conversation_llm",
    "encoded_size",
]
