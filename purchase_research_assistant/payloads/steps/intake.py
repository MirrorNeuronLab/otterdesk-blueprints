from __future__ import annotations

from mn_sdk.step_runtime import StepContext

from mn_blueprint_support import get_actor_llm_client

from runtime import runtime
from ._shared import runtime_inputs, step_result


def run(context: StepContext) -> dict:
    config, inputs, input_source = runtime_inputs(context)
    root = runtime._script_blueprint_root()
    folder = runtime.resolve_input_folder(config, inputs, root)
    documents, warnings = runtime.load_input_documents(folder, config)
    knowledge = runtime.load_purchase_knowledge(root)
    llm = get_actor_llm_client(config, None)
    intake_plan = runtime.ask_llm_for_intake(llm, inputs, documents, knowledge)
    payload = {
        "inputs": inputs,
        "input_source": input_source,
        "documents": documents,
        "document_warnings": warnings,
        "knowledge": knowledge,
        "intake_plan": intake_plan,
    }
    return step_result(context, payload, document_count=len(documents))
