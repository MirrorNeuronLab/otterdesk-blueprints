from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._state import build_stage_context, result


def run(context: StepContext, operation: str) -> dict[str, Any]:
    ctx = build_stage_context(context)
    if operation == "watch":
        runtime.write_json(
            ctx["run_dir"] / "run.json",
            {"run_id": ctx["run_id"], "blueprint_id": runtime.BLUEPRINT_ID, "status": "running", "started_at": runtime.utc_now_iso()},
        )
        runtime.write_json(ctx["run_dir"] / "config.json", ctx["config"])
        runtime.write_json(
            ctx["run_dir"] / "inputs.json",
            {"payload": ctx["payload"], "document_folder": str(ctx["document_folder"]), "dataset_inputs": runtime.DATASET_INPUTS},
        )
        return result(ctx, document_folder=str(ctx["document_folder"]))
    if operation == "read":
        llm = runtime.build_llm_client(ctx["config"], ctx["payload"], None)
        ocr_client, ocr_status = runtime.build_ocr_runtime({"config": ctx["config"], "payload": ctx["payload"], "llm": llm})
        records = runtime.load_documents(ctx["document_folder"], ocr_client=ocr_client)
        ctx["state"].update(
            {
                "records": records,
                "evidence": runtime.summarize_records(records),
                "warnings": runtime.record_warnings(records),
                "ocr_status": ocr_status,
            }
        )
        return result(ctx, document_count=len(records), warning_count=len(ctx["state"]["warnings"]))
    raise ValueError(f"unknown legal intake operation: {operation}")
