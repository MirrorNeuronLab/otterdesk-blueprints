"""Shared constants and small helpers for the Research Co-Scientist."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

RUNTIME_SKILL_PACKAGES = (
    "mirrorneuron-blueprint-support-skill",
    "mirrorneuron-llm-ocr-skill",
    "mirrorneuron-rag-skill",
    "mirrorneuron-w3m-browser-skill",
    "mirrorneuron-web-browser-skill",
    "mirrorneuron-autonomous-research-skill",
)

def _bootstrap_runtime() -> None:
    for parent in Path(__file__).resolve().parents:
        helper = parent / "otterdesk_blueprint_env.py"
        if helper.exists():
            spec = importlib.util.spec_from_file_location("otterdesk_blueprint_env", helper)
            if spec is None or spec.loader is None:
                return
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            module.bootstrap_blueprint_runtime(__file__, packages=RUNTIME_SKILL_PACKAGES)
            return

_bootstrap_runtime()

from mn_blueprint_support import DeterministicFallbackLLM, PromptLibrary, get_actor_llm_client, get_llm_client
from mn_sdk.blueprint_support import source_manifest


BLUEPRINT_ID = "research_coscientist"


BLUEPRINT_NAME = "Research Co-Scientist"


CATEGORY = "Science"


OUTPUT_TYPE = "research_coscientist_packet"


DEFAULT_OUTPUT_FOLDER = "~/Downloads/research_coscientist"


SUPPORTED_SUFFIXES = {".pdf", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".webp", ".txt", ".md", ".json", ".csv"}


TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv"}


RESEARCH_ACTIONS = {"review_research_packet", "gather_more_evidence"}


_SOURCE_MANIFEST = source_manifest(__file__)
BLOCKED_ACTIONS = list(
    (((_SOURCE_MANIFEST.get("workflow") or {}).get("policy") or {}).get("human") or {}).get("blocked_actions")
    or []
)


PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)


class QuickTestLLM(DeterministicFallbackLLM):
    def __init__(self) -> None:
        super().__init__(
            "deterministic-research-coscientist",
            default_summary="Deterministic research review completed from approved local evidence.",
            confidence=0.7,
        )


def quick_test_enabled(config: dict[str, Any]) -> bool:
    execution = config.get("execution") if isinstance(config.get("execution"), dict) else {}
    llm = config.get("llm") if isinstance(config.get("llm"), dict) else {}
    return bool(execution.get("quick_test")) or str(llm.get("mode") or "").lower() in {"fake", "mock", "test"}


def research_llm(config: dict[str, Any], provided: Any | None = None, *, actor: bool = False) -> Any:
    if provided is not None:
        return provided
    if quick_test_enabled(config):
        return QuickTestLLM()
    return get_actor_llm_client(config, None) if actor else get_llm_client(None)


def load_prompt(name: str) -> str:
    return PROMPTS.load(name)


def _script_blueprint_root() -> Path:
    script = Path(__file__).resolve()
    for parent in script.parents:
        if (parent / "manifest.json").exists():
            return parent
    return script.parents[3]


def runtime_asset_root() -> Path:
    """Return the self-contained directory uploaded to every workflow worker."""
    return Path(__file__).resolve().parents[1]


def default_config_path() -> Path:
    configured = os.environ.get("MN_BLUEPRINT_CONFIG_PATH")
    if configured and Path(configured).expanduser().exists():
        return Path(configured).expanduser()
    bundle = os.environ.get("MN_BLUEPRINT_BUNDLE_DIR")
    if bundle and (Path(bundle).expanduser() / "config" / "default.json").exists():
        return Path(bundle).expanduser() / "config" / "default.json"
    if os.environ.get("MN_BLUEPRINT_CONFIG_JSON"):
        # Docker worker attempts may carry embedded config without mounting
        # the bundle's config file. Resolve relative to the attempt root.
        return Path(__file__).resolve().parents[2] / "config" / "default.json"
    return _script_blueprint_root() / "config" / "default.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _sha256(value: str | bytes) -> str:
    raw = value.encode("utf-8") if isinstance(value, str) else value
    return hashlib.sha256(raw).hexdigest()


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


__all__ = ['BLUEPRINT_ID', 'BLUEPRINT_NAME', 'CATEGORY', 'OUTPUT_TYPE', 'DEFAULT_OUTPUT_FOLDER', 'SUPPORTED_SUFFIXES', 'TEXT_SUFFIXES', 'RESEARCH_ACTIONS', 'BLOCKED_ACTIONS', 'PROMPTS', 'QuickTestLLM', 'quick_test_enabled', 'research_llm', 'load_prompt', '_script_blueprint_root', 'runtime_asset_root', 'default_config_path', '_now', '_sha256', '_json_safe', '_compact']
