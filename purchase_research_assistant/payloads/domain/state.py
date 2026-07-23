"""Durable run-state access shared by purchase specialists."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

from .inputs import normalize_inputs

STATE_FILE = "purchase_research_state.json"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    return normalize_inputs({**((ctx["config"].get("inputs") or {}).get("payload") or {}), **ctx["payload"]})


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)
