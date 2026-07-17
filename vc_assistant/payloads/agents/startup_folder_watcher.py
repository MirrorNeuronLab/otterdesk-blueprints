from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import write_workflow_state
from domain.common import (
    SUPPORTED_SUFFIXES,
)
from domain.intake import _document_paths
from domain.runtime_tools import (
    append_event,
    observed_operation,
    stable_text_hash,
)

from ._shared import agent_output, create_agent_handler, durable_artifact


def run_startup_folder_watcher(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    ctx["run_dir"].mkdir(parents=True, exist_ok=True)
    ctx["output_folder"].mkdir(parents=True, exist_ok=True)
    append_event(
        ctx["run_dir"],
        "watch_cycle_started",
        {"cycle": 1, "max_cycles": ctx["max_cycles"]},
    )
    with observed_operation(
        ctx["run_dir"],
        phase="startup_folder_watcher",
        operation="discover_document_files",
        path_hash=stable_text_hash(ctx["document_folder"]),
        supported_suffixes=sorted(SUPPORTED_SUFFIXES),
    ) as op:
        files = [
            {
                "path": str(path),
                "relative_path": str(path.relative_to(ctx["document_folder"]))
                if path.is_relative_to(ctx["document_folder"])
                else path.name,
                "suffix": path.suffix.lower(),
                "size_bytes": path.stat().st_size,
                "mtime": path.stat().st_mtime,
            }
            for path in _document_paths(ctx["document_folder"])
        ]
        write_workflow_state(ctx["run_dir"], "document_files.json", files)
        op.close("completed", document_file_count=len(files))
    artifact = durable_artifact(
        "document_file_index", "workflow_state/document_files.json"
    )
    return agent_output(
        {
            "document_file_count": len(files),
            "document_folder": str(ctx["document_folder"]),
            "document_files_artifact": artifact,
        },
        artifact,
        metrics={"document_file_count": len(files)},
    )


run = create_agent_handler(run_startup_folder_watcher)
