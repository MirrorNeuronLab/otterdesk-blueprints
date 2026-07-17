"""Purchase research domain operations with durable artifact-backed state."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_blueprint_support import get_actor_llm_client, resolve_actor_specs, run_actor_reviews
from mn_sdk.blueprint_support import WorkflowStateStore

from . import legacy


STATE_FILE = "purchase_research_state.json"


def _inputs(ctx: dict[str, Any]) -> dict[str, Any]:
    return legacy.normalize_inputs({**((ctx["config"].get("inputs") or {}).get("payload") or {}), **ctx["payload"]})


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    return WorkflowStateStore(Path(ctx["run_dir"])).read(STATE_FILE, {})


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)


def collect_context(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    folder = legacy.resolve_input_folder(ctx["config"], inputs, root)
    documents, warnings = legacy.load_input_documents(folder, ctx["config"])
    knowledge = legacy.load_purchase_knowledge(root)
    llm = get_actor_llm_client(ctx["config"], None)
    intake_plan = legacy.ask_llm_for_intake(llm, inputs, documents, knowledge)
    state = {"inputs": inputs, "documents": documents, "document_warnings": warnings, "knowledge": knowledge, "intake_plan": intake_plan}
    _save(ctx, state)
    return {"document_count": len(documents)}


def retrieve_knowledge(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    documents = state.get("documents") or []
    knowledge = state.get("knowledge") or legacy.load_purchase_knowledge(root)
    rag = legacy.prepare_purchase_rag(ctx["config"], root, knowledge, documents, ctx["run_id"])
    queries = legacy.build_public_queries(inputs, state.get("intake_plan") or {})
    retrieval = legacy.retrieve_purchase_rag_context(" ".join(queries), rag, knowledge, documents, max_chars=int((ctx["config"].get("knowledge_rag") or {}).get("max_context_chars", 6000)))
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
    sources, web_warnings = legacy.research_public_sources(state.get("research_queries") or [], ctx["config"], quick_test=quick)
    documents = state.get("documents") or []
    evidence = legacy.deterministic_evidence(inputs, documents, sources)
    deterministic = legacy.deterministic_recommendation(evidence, sources)
    llm = get_actor_llm_client(ctx["config"], None)
    recommendation = legacy.ask_llm_for_recommendation(llm, inputs, evidence, state.get("rag") or {}, deterministic)
    actor_findings = run_actor_reviews(
        config=ctx["config"], llm=llm, actor_ids=list(resolve_actor_specs(ctx["config"]).keys()), state={},
        task=legacy.load_prompt("purchase-review-task.md"),
        context={"inputs": inputs, "intake_plan": state.get("intake_plan") or {}, "evidence": evidence, "recommendation": recommendation, "rag": state.get("rag") or {}, "sources": sources},
    )
    state.update({"inputs": inputs, "sources": sources, "web_warnings": web_warnings, "evidence": evidence, "recommendation": recommendation, "actor_findings": actor_findings, "llm_usage": legacy.llm_usage(llm)})
    _save(ctx, state)
    return {"source_count": len(sources)}


def publish_report(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
    warnings = [*(state.get("document_warnings") or []), *((state.get("rag") or {}).get("warnings") or []), *(state.get("web_warnings") or [])]
    final = legacy.build_final_artifact(inputs, state.get("evidence") or {}, state.get("recommendation") or {}, state.get("rag") or {}, state.get("sources") or [], warnings, state.get("documents") or [], state.get("actor_findings") or {}, ctx["run_id"], intake_plan=state.get("intake_plan") or {})
    result = {
        "identity": {"blueprint_id": legacy.BLUEPRINT_ID, "name": legacy.BLUEPRINT_NAME, "run_id": ctx["run_id"]},
        "blueprint": legacy.BLUEPRINT_ID, "name": legacy.BLUEPRINT_NAME, "category": legacy.CATEGORY,
        "run": {"run_id": ctx["run_id"], "status": "completed"}, "inputs": inputs,
        "intake_plan": state.get("intake_plan") or {}, "knowledge_rag": state.get("rag") or {},
        "research_sources": state.get("sources") or [], "evidence": state.get("evidence") or {},
        "recommendation": state.get("recommendation") or {}, "final_artifact": final,
        "llm": state.get("llm_usage") or {},
    }
    final["llm_usage"] = result["llm"]
    output_files = legacy.write_user_outputs(final, result, ctx["config"], inputs)
    result["output_files"] = output_files
    _save(ctx, state)
    return {"final_artifact": final, "output_files": output_files}

