"""Purchase decision framing and approved evidence retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .inputs import load_input_documents, resolve_input_folder, resolve_request_from_documents
from .knowledge import load_purchase_knowledge, prepare_purchase_rag, retrieve_purchase_rag_context
from .llm_analysis import generate_structured_analysis
from .research import _normalize_intake_plan, build_public_queries
from .state import _inputs, _save, _state


def _validate_intake_plan(
    response: Any, fallback: dict[str, Any], _settings: dict[str, Any]
) -> tuple[dict[str, Any], list[str]]:
    if not isinstance(response, dict):
        return dict(fallback), ["intake_plan: expected object"]
    normalized = dict(fallback)
    for key in ("normalized_goal", "category"):
        value = str(response.get(key) or "").strip()
        if value:
            normalized[key] = value[:500]
    for key in (
        "must_haves",
        "deal_breakers",
        "decision_criteria",
        "research_questions",
        "public_query_topics",
        "unknowns",
        "technical_requirements",
        "commercial_requirements",
        "required_approvals",
    ):
        values = response.get(key)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            cleaned = [str(item).strip()[:400] for item in values if str(item).strip()]
            normalized[key] = list(dict.fromkeys(cleaned))[:12]
    return normalized, []


def collect_context(
    ctx: dict[str, Any], *, llm_client: Any | None = None, **_options: Any
) -> dict[str, Any]:
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    folder = resolve_input_folder(ctx["config"], inputs, root)
    documents, warnings = load_input_documents(folder, ctx["config"])
    inputs, request = resolve_request_from_documents(inputs, documents)
    knowledge = load_purchase_knowledge(root)
    state = {
        "inputs": inputs,
        "request": request,
        "research_links": request["research_links"],
        "documents": documents,
        "document_warnings": warnings,
        "knowledge": knowledge,
    }
    fallback = _normalize_intake_plan({}, inputs)
    intake_plan = generate_structured_analysis(
        state=state,
        config=ctx["config"],
        agent_id="purchase_intake_analyst",
        prompt_name="purchase-intake-task.md",
        payload={
            "inputs": inputs,
            "local_evidence": [
                {
                    "source_ref": item.get("source_ref"),
                    "name": item.get("name"),
                    "suffix": item.get("suffix"),
                    "text_included": False,
                }
                for item in documents[:8]
            ],
            "available_guidance": [item.get("name") for item in knowledge.get("files") or []],
            "authoritative_boundaries": {
                "local_document_text_included": False,
                "deterministic_values_immutable": True,
            },
            "output_contract": list(fallback),
        },
        fallback=fallback,
        validator=_validate_intake_plan,
        llm_client=llm_client,
    )
    state["intake_plan"] = intake_plan
    _save(ctx, state)
    return {
        "document_count": len(documents),
        "request_source_ref": request["source_ref"],
        "research_link_count": len(request["research_links"]),
    }


def retrieve_knowledge(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    documents = state.get("documents") or []
    knowledge = state.get("knowledge") or load_purchase_knowledge(root)
    rag = prepare_purchase_rag(ctx["config"], root, knowledge, documents, ctx["run_id"])
    queries = build_public_queries(inputs, state.get("intake_plan") or {})
    retrieval = retrieve_purchase_rag_context(" ".join(queries), rag, knowledge, documents, max_chars=int((ctx["config"].get("knowledge_rag") or {}).get("max_context_chars", 6000)))
    rag.update({key: retrieval[key] for key in ("context", "citations", "chunks")})
    if retrieval.get("warning"):
        rag.setdefault("warnings", []).append(retrieval["warning"])
    rag.pop("_rag_config", None)
    state.update({"inputs": inputs, "knowledge": knowledge, "rag": rag, "research_queries": queries})
    _save(ctx, state)
    return {"citation_count": len(rag.get("citations") or [])}
