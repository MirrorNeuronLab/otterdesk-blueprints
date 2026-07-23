"""Purchase decision framing and approved evidence retrieval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .common import purchase_llm
from .inputs import load_input_documents, resolve_input_folder
from .knowledge import load_purchase_knowledge, prepare_purchase_rag, retrieve_purchase_rag_context
from .research import ask_llm_for_intake, build_public_queries
from .state import _inputs, _save, _state

def collect_context(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    inputs = _inputs(ctx)
    root = Path(ctx["blueprint_dir"])
    folder = resolve_input_folder(ctx["config"], inputs, root)
    documents, warnings = load_input_documents(folder, ctx["config"])
    knowledge = load_purchase_knowledge(root)
    llm = purchase_llm(ctx["config"])
    intake_plan = ask_llm_for_intake(llm, inputs, documents, knowledge)
    state = {"inputs": inputs, "documents": documents, "document_warnings": warnings, "knowledge": knowledge, "intake_plan": intake_plan}
    _save(ctx, state)
    return {"document_count": len(documents)}


def retrieve_knowledge(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = _inputs(ctx)
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
