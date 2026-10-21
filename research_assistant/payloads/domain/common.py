"""Shared constants and small helpers for the Research Assistant."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


from mn_sdk.blueprint_support import DeterministicFallbackLLM
from mn_sdk_common.prompts import PromptLibrary
from mn_prototype_actor_review_agent.actors import get_actor_llm_client
from mn_sdk.blueprint_support import source_manifest, BlueprintBundleLayout


_SOURCE_MANIFEST = source_manifest(__file__)
INPUT_KEYS = frozenset(_SOURCE_MANIFEST["contracts"]["inputs"])
BLUEPRINT_ID = _SOURCE_MANIFEST["identity"]["id"]


BLUEPRINT_NAME = _SOURCE_MANIFEST["identity"]["name"]


OUTPUT_TYPE = "research_assistant_packet"


DEFAULT_OUTPUT_FOLDER = _SOURCE_MANIFEST["config"]["data"]["outputs"]["folder_path"]


SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".md", ".json", ".csv"}


TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}


RESEARCH_ACTIONS = {"review_research_packet", "gather_more_evidence"}


BLOCKED_ACTIONS = list(
    (((_SOURCE_MANIFEST.get("workflow") or {}).get("policy") or {}).get("human") or {}).get("blocked_actions")
    or []
)


PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)


def quick_test_enabled(config: dict[str, Any]) -> bool:
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    return bool(execution.get("quick_test")) or str(llm.get("mode") or "").lower() in {"fake", "mock", "test"}


def research_llm(config: dict[str, Any], provided: Any | None = None) -> Any:
    if provided is not None:
        return provided
    if quick_test_enabled(config):
        return DeterministicFallbackLLM("deterministic-research-assistant",
            default_summary="Deterministic research review completed from approved local evidence.", confidence=.7)
    return get_actor_llm_client(config, None)


def load_prompt(name: str) -> str:
    return PROMPTS.load(name)


def runtime_asset_root() -> Path:
    return BlueprintBundleLayout.discover(__file__).payload_root


def _json_safe(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        if isinstance(value, dict):
            return {str(k): _json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_json_safe(v) for v in value]
        return str(value)


def _compact(value: Any, limit: int = 1800) -> str:
    text = value if isinstance(value, str) else json.dumps(_json_safe(value), sort_keys=True, default=str)
    return text if len(text) <= limit else text[: limit - 3] + "..."
