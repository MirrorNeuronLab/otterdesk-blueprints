from __future__ import annotations

from mn_sdk.step_runtime import StepContext

from runtime import runtime
from ._shared import previous_payload, runtime_inputs, step_result


def run(context: StepContext) -> dict:
    config, inputs, _input_source = runtime_inputs(context)
    previous = previous_payload(context)
    documents = previous.get("documents") or []
    knowledge = previous.get("knowledge") or runtime.load_purchase_knowledge(runtime._script_blueprint_root())
    intake_plan = previous.get("intake_plan") or {}
    rag = runtime.prepare_purchase_rag(config, runtime._script_blueprint_root(), knowledge, documents, context.run_id or None)
    queries = runtime.build_public_queries(inputs, intake_plan)
    retrieval = runtime.retrieve_purchase_rag_context(
        " ".join(queries),
        rag,
        knowledge,
        documents,
        max_chars=int((config.get("knowledge_rag") or {}).get("max_context_chars", 6000)),
    )
    rag.update({key: retrieval[key] for key in ("context", "citations", "chunks")})
    if retrieval.get("warning"):
        rag.setdefault("warnings", []).append(retrieval["warning"])
    rag.pop("_rag_config", None)
    payload = {**previous, "inputs": inputs, "rag": rag, "research_queries": queries}
    return step_result(context, payload, citation_count=len(rag.get("citations") or []))
