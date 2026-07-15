from __future__ import annotations

from typing import Any

from mn_blueprint_support import start_agent_beacon_thread
from mn_sdk.blueprint_support import write_json, write_workflow_state
from runtime.runtime import (
    BLUEPRINT_ID,
    BLUEPRINT_NAME,
    SUPPORTED_SUFFIXES,
    _document_paths,
    append_event,
    observed_operation,
    persist_runtime_context,
    stable_text_hash,
)

def run_startup_folder_watcher(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    start_agent_beacon_thread(f"{BLUEPRINT_NAME} is running")
    ctx["run_dir"].mkdir(parents=True, exist_ok=True)
    ctx["output_folder"].mkdir(parents=True, exist_ok=True)
    persist_runtime_context(ctx)
    write_json(ctx["run_dir"] / "config.json", ctx["config"])
    write_json(
        ctx["run_dir"] / "inputs.json",
        {"payload": ctx["payload"], "document_folder": str(ctx["document_folder"]), "force_reprocess": ctx["force_reprocess"]},
    )
    write_json(ctx["run_dir"] / "run.json", {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "running", "started_at": ctx["started_at"]})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "blueprint_phase_completed", {"phase": "loading_inputs", "component": BLUEPRINT_ID})
    append_event(ctx["run_dir"], "watch_cycle_started", {"cycle": 1, "max_cycles": ctx["max_cycles"]})
    append_event(ctx["run_dir"], "blueprint_phase_started", {"phase": "running_worker", "component": BLUEPRINT_ID})
    with observed_operation(ctx["run_dir"], phase="startup_folder_watcher", operation="discover_document_files", path_hash=stable_text_hash(ctx["document_folder"]), supported_suffixes=sorted(SUPPORTED_SUFFIXES)) as op:
        files = [
            {
                "path": str(path),
                "relative_path": str(path.relative_to(ctx["document_folder"])) if path.is_relative_to(ctx["document_folder"]) else path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
            for path in _document_paths(ctx["document_folder"])
        ]
        write_workflow_state(ctx["run_dir"], "document_files.json", files)
        op.close("completed", document_file_count=len(files))
    return {"document_file_count": len(files), "document_folder": str(ctx["document_folder"])}
