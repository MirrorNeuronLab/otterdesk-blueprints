"""Small durable state helpers shared by the bounded advisory workers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

STATE_FILE = "software_architecture_advisor_state.json"


def inputs_for(ctx: dict[str, Any]) -> dict[str, Any]:
    configured = ((ctx.get("config") or {}).get("inputs") or {}).get("payload") or {}
    # The runtime carries every optional contract input in its payload, using
    # null for values the operator did not supply. A null is absence, not an
    # explicit override of the blueprint's configured default.
    supplied = {
        key: value
        for key, value in dict(ctx.get("payload") or {}).items()
        if value is not None
    }
    merged = {**configured, **supplied}
    # A URL is the user's source selection. The platform must replace the
    # bundled demo folder with a materialized snapshot before analysis starts.
    if supplied.get("github_repo_url") and "input_folder" not in supplied:
        merged["input_folder"] = ""
    merged["input_folder"] = str(merged.get("input_folder") or "").strip()
    merged["github_repo_url"] = str(merged.get("github_repo_url") or "").strip()
    merged["branch"] = str(merged.get("branch") or "main").strip() or "main"
    focus = merged.get("analysis_focus") or []
    merged["analysis_focus"] = [str(item).strip() for item in (focus if isinstance(focus, list) else [focus]) if str(item).strip()]
    merged["output_folder"] = str(merged.get("output_folder") or "").strip()
    return merged


def source_root_for_context(ctx: dict[str, Any]) -> Path:
    """Resolve this worker's own staged source directory.

    Docker workers receive independent payload workspaces.  A durable workflow
    state may therefore contain the absolute source path used by a previous
    worker, which must never be reused by a later worker.
    """
    folder = Path(inputs_for(ctx)["input_folder"]).expanduser().resolve()
    if not folder.is_dir():
        raise ValueError("The staged source root must be an existing directory.")
    return folder


def read_state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def write_state(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)
