from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore, create_blueprint_run_context
from mn_sdk.step_runtime import StepContext

from runtime import runtime


STATE_FILE = "legal_workflow_state.json"


def build_stage_context(context: StepContext) -> dict[str, Any]:
    base = create_blueprint_run_context(
        runtime_file=runtime.__file__,
        blueprint_id=runtime.BLUEPRINT_ID,
        inputs=runtime.find_payload(context.message),
        config=context.config or None,
        run_id=context.run_id or None,
    )
    root = base.layout.root
    config = base.config
    payload = base.payload
    run_id = base.run_id
    document_folder = runtime.expand_runtime_path(
        payload.get("document_folder") or payload.get("input_folder") or "examples/sample_inputs"
    )
    if not document_folder.is_absolute():
        document_folder = root / document_folder
    output_folder = base.output_folder
    run_dir = base.run_dir
    state = WorkflowStateStore(run_dir).read(STATE_FILE, {})
    state.update(
        {
            "run_id": run_id,
            "document_folder": str(document_folder),
            "output_folder": str(output_folder),
            "workflow_step_id": context.step_id,
        }
    )
    return {
        "root": root,
        "config": config,
        "payload": payload,
        "run_id": run_id,
        "document_folder": document_folder,
        "output_folder": output_folder,
        "run_dir": run_dir,
        "state": state,
        "workflow_step_id": context.step_id,
    }


def save(ctx: dict[str, Any]) -> None:
    WorkflowStateStore(ctx["run_dir"]).write(STATE_FILE, ctx["state"])


def result(ctx: dict[str, Any], **outputs: Any) -> dict[str, Any]:
    save(ctx)
    return {
        "run_id": ctx["run_id"],
        "status": "completed",
        "workflow_step_id": ctx["workflow_step_id"],
        "outputs": outputs,
    }
