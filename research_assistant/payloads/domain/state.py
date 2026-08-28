"""Durable research-state access shared by bounded specialists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

from .inputs import normalize_inputs

STATE_FILE = "research_assistant_state.json"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    configured = ((ctx["config"].get("inputs") or {}).get("payload") or {})
    payload = ctx.get("payload") if isinstance(ctx.get("payload"), dict) else {}
    overrides = {
        key: value
        for key, value in payload.items()
        if _has_runtime_value(value)
    }
    return normalize_inputs({**configured, **overrides})


def _has_runtime_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (dict, list, tuple, set)):
        return bool(value)
    return True


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)
