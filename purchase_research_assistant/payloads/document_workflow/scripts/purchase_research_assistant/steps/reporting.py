from __future__ import annotations

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._shared import previous_payload, runtime_inputs


def run(context: StepContext) -> dict:
    config, inputs, input_source = runtime_inputs(context)
    previous = previous_payload(context)
    warnings = [
        *(previous.get("document_warnings") or []),
        *((previous.get("rag") or {}).get("warnings") or []),
        *(previous.get("web_warnings") or []),
    ]
    final = runtime.build_final_artifact(
        inputs,
        previous.get("evidence") or {},
        previous.get("recommendation") or {},
        previous.get("rag") or {},
        previous.get("sources") or [],
        warnings,
        previous.get("documents") or [],
        previous.get("actor_findings") or {},
        context.run_id,
        intake_plan=previous.get("intake_plan") or {},
    )
    result = {
        "identity": {"blueprint_id": runtime.BLUEPRINT_ID, "name": runtime.BLUEPRINT_NAME, "run_id": context.run_id},
        "blueprint": runtime.BLUEPRINT_ID,
        "name": runtime.BLUEPRINT_NAME,
        "category": runtime.CATEGORY,
        "run": {"run_id": context.run_id, "status": "completed"},
        "architecture": runtime.architecture_contract(config, input_source),
        "config": config,
        "inputs": inputs,
        "intake_plan": previous.get("intake_plan") or {},
        "knowledge_rag": previous.get("rag") or {},
        "research_sources": previous.get("sources") or [],
        "evidence": previous.get("evidence") or {},
        "recommendation": previous.get("recommendation") or {},
        "final_artifact": final,
        "llm": previous.get("llm_usage") or {},
    }
    final["llm_usage"] = result["llm"]
    output_files = runtime.write_user_outputs(final, result, config, inputs)
    if output_files:
        result["output_files"] = output_files
    return {"run_id": context.run_id, "status": "completed", "workflow_step_id": context.step_id, "final_artifact": final, "output_files": output_files}
