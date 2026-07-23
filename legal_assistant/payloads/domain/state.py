"""Durable, lane-isolated legal workflow state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

from .runtime_services import expand_runtime_path


STATE_FILES = (
    "legal_matter_state.json",
    "legal_invoice_lane.json",
    "legal_contract_lane.json",
    "legal_review_state.json",
)


def load_state(ctx: dict[str, Any]) -> dict[str, Any]:
    store = WorkflowStateStore(Path(ctx["run_dir"]))
    state: dict[str, Any] = {}
    for filename in STATE_FILES:
        value = store.read(filename, {})
        if isinstance(value, dict):
            state.update(value)
    state.update({
        "run_id": ctx["run_id"],
        "document_folder": str(expand_runtime_path(ctx["payload"].get("document_folder") or ctx["payload"].get("input_folder") or "examples/sample_inputs")),
        "output_folder": str(ctx["output_folder"]),
    })
    return state


def save_state(ctx: dict[str, Any], state: dict[str, Any], filename: str) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(filename, state)
