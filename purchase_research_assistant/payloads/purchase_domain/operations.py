"""Purchase research domain operations with durable artifact-backed state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_blueprint_support import get_actor_llm_client, resolve_actor_specs, run_actor_reviews
from mn_sdk.blueprint_support import WorkflowStateStore

from . import workflow


STATE_FILE = "purchase_research_state.json"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    return workflow.normalize_inputs({**((ctx["config"].get("inputs") or {}).get("payload") or {}), **ctx["payload"]})


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)


def collect_context(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    folder = workflow.resolve_input_folder(ctx["config"], inputs, root)
    documents, warnings = workflow.load_input_documents(folder, ctx["config"])
    knowledge = workflow.load_purchase_knowledge(root)
    llm = get_actor_llm_client(ctx["config"], None)
    intake_plan = workflow.ask_llm_for_intake(llm, inputs, documents, knowledge)
    state = {"inputs": inputs, "documents": documents, "document_warnings": warnings, "knowledge": knowledge, "intake_plan": intake_plan}
    _save(ctx, state)
    return {"document_count": len(documents)}


def retrieve_knowledge(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    documents = state.get("documents") or []
    knowledge = state.get("knowledge") or workflow.load_purchase_knowledge(root)
    rag = workflow.prepare_purchase_rag(ctx["config"], root, knowledge, documents, ctx["run_id"])
    queries = workflow.build_public_queries(inputs, state.get("intake_plan") or {})
    retrieval = workflow.retrieve_purchase_rag_context(" ".join(queries), rag, knowledge, documents, max_chars=int((ctx["config"].get("knowledge_rag") or {}).get("max_context_chars", 6000)))
    rag.update({key: retrieval[key] for key in ("context", "citations", "chunks")})
    if retrieval.get("warning"):
        rag.setdefault("warnings", []).append(retrieval["warning"])
    rag.pop("_rag_config", None)
    state.update({"inputs": inputs, "knowledge": knowledge, "rag": rag, "research_queries": queries})
    _save(ctx, state)
    return {"citation_count": len(rag.get("citations") or [])}


def research_options(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    llm_config = ctx["config"].get("llm") if isinstance(ctx["config"].get("llm"), dict) else {}
    quick = str(llm_config.get("mode") or "live").lower() in {"fake", "mock"} or bool((ctx["config"].get("execution") or {}).get("quick_test"))
    sources, web_warnings = workflow.research_public_sources(state.get("research_queries") or [], ctx["config"], quick_test=quick)
    documents = state.get("documents") or []
    evidence = workflow.deterministic_evidence(inputs, documents, sources)
    deterministic = workflow.deterministic_recommendation(evidence, sources)
    llm = get_actor_llm_client(ctx["config"], None)
    recommendation = workflow.ask_llm_for_recommendation(llm, inputs, evidence, state.get("rag") or {}, deterministic)
    actor_findings = run_actor_reviews(
        config=ctx["config"], llm=llm, actor_ids=list(resolve_actor_specs(ctx["config"]).keys()), state={},
        task=workflow.load_prompt("purchase-review-task.md"),
        context={"inputs": inputs, "intake_plan": state.get("intake_plan") or {}, "evidence": evidence, "recommendation": recommendation, "rag": state.get("rag") or {}, "sources": sources},
    )
    state.update({"inputs": inputs, "sources": sources, "web_warnings": web_warnings, "evidence": evidence, "recommendation": recommendation, "actor_findings": actor_findings, "llm_usage": workflow.llm_usage(llm)})
    _save(ctx, state)
    return {"source_count": len(sources)}


def publish_report(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    warnings = [*(state.get("document_warnings") or []), *((state.get("rag") or {}).get("warnings") or []), *(state.get("web_warnings") or [])]
    final = workflow.build_final_artifact(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], warnings, state.get("documents") or [], state.get("actor_findings") or {}, ctx["run_id"], intake_plan=state.get("intake_plan") or {})
    result = {
        "identity": {"blueprint_id": workflow.BLUEPRINT_ID, "name": workflow.BLUEPRINT_NAME, "run_id": ctx["run_id"]},
        "blueprint": workflow.BLUEPRINT_ID, "name": workflow.BLUEPRINT_NAME, "category": workflow.CATEGORY,
        "run": {"run_id": ctx["run_id"], "status": "completed"}, "inputs": inputs,
        "intake_plan": state.get("intake_plan") or {}, "knowledge_rag": state.get("rag") or {},
        "research_sources": state.get("sources") or [], "evidence": state.get("evidence") or {},
        "recommendation": state.get("recommendation") or {}, "final_artifact": final,
        "llm": state.get("llm_usage") or {},
    }
    final["llm_usage"] = result["llm"]
    output_files = workflow.write_user_outputs(final, result, ctx["config"], inputs)
    result["output_files"] = output_files
    _save(ctx, state)
    return {"final_artifact": final, "output_files": output_files}

