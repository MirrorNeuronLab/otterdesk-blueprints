from __future__ import annotations

import os
import uuid
from pathlib import Path
from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime


STATE_FILE = "legal_workflow_state.json"


def build_stage_context(context: StepContext) -> dict[str, Any]:
    root = runtime.blueprint_dir()
    config = runtime.load_resolved_config(context.config or None)
    payload = runtime.resolve_inputs(config, runtime.find_payload(context.message))
    run_id = context.run_id or str(payload.get("run_id") or os.environ.get("MN_JOB_ID") or f"{runtime.BLUEPRINT_ID}-{uuid.uuid4().hex[:8]}")
    document_folder = runtime.expand_path(
        payload.get("document_folder") or payload.get("input_folder") or "examples/sample_inputs",
        root=root,
    )
    output_folder = runtime.resolve_output_folder(payload, config, None)
    run_dir = runtime.resolve_run_dir(output_folder, run_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    state = runtime.read_json(run_dir / STATE_FILE)
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
    runtime.write_json(ctx["run_dir"] / STATE_FILE, ctx["state"])


def result(ctx: dict[str, Any], **outputs: Any) -> dict[str, Any]:
    save(ctx)
    return {
        "run_id": ctx["run_id"],
        "status": "completed",
        "workflow_step_id": ctx["workflow_step_id"],
        "outputs": outputs,
    }
