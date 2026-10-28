"""Purchase decision framing and approved evidence retrieval."""

from __future__ import annotations

import json
from jsonschema import validate
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.integrations.block_inputs import save_declared_inputs
from mn_sdk.agent_events import report_activity
from mn_sdk.integrations.block_inputs import configured_input_path

from typing import Any

from .inputs import load_input_documents, resolve_request_from_documents
from .knowledge import load_purchase_knowledge, prepare_purchase_rag, retrieve_purchase_rag_context
from .llm_analysis import generate_structured_analysis
from .research import _normalize_intake_plan, build_public_queries
from .state import purchase_inputs, save_state, read_state, bundle_layout
from .common import BLUEPRINT_ID


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
    block, inputs, *, llm_client: Any | None = None
) -> dict[str, Any]:
    report_activity("Collecting purchase requirements", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    block.check()
    llm_client = llm_client or block.resources.get("llm")
    inputs = purchase_inputs(block, inputs["request"])
    instructions = inputs.get("supervisor_instructions", [])
    declaration = source_manifest(__file__)["contracts"]["inputs"]["supervisor_instructions"]
    validate(instructions, {key: value for key, value in declaration.items() if key != "required"})
    if len(json.dumps(instructions, ensure_ascii=False, separators=(",", ":")).encode()) > 16000 or len({item["id"] for item in instructions}) != len(instructions):
        raise ValueError("Saved purchasing review instructions exceed the supported bounds")
    layout = bundle_layout()
    folder = configured_input_path(block.config, inputs, "input_folder", runtime_file=__file__, environment=block.environment)
    documents, warnings = load_input_documents(folder, block.config)
    inputs, request = resolve_request_from_documents(inputs, documents)
    knowledge = load_purchase_knowledge(layout.payload_root / "knowledge")
    state = {
        "input_artifact": save_declared_inputs(block, inputs, runtime_file=__file__).to_dict(),
        "inputs": inputs,
        "supervisor_instruction_revision": fingerprint(instructions),
        "request": request,
        "research_links": request["research_links"],
        "documents": documents,
        "document_warnings": warnings,
        "knowledge": knowledge,
    }
    fallback = _normalize_intake_plan({}, inputs)
    intake_plan = generate_structured_analysis(
        state=state,
        config=block.config,
        agent_id="purchase_intake_analyst",
        prompt_name="purchase-intake-task.md",
        payload={
            "inputs": {key: value for key, value in inputs.items() if key != "supervisor_instructions"},
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
    return {
        "state": save_state(block, state, "intake"),
        "document_count": len(documents),
        "request_source_ref": request["source_ref"],
        "research_link_count": len(request["research_links"]),
    }


def retrieve_knowledge(block, inputs) -> dict[str, Any]:
    report_activity("Retrieving purchase policy and evidence", owner_blueprint=BLUEPRINT_ID, run_dir=block.store.run_dir)
    state = read_state(block, inputs["previous"])
    inputs = state["inputs"]
    layout = bundle_layout()
    root = layout.root
    documents = state.get("documents") or []
    knowledge = state.get("knowledge") or load_purchase_knowledge(layout.payload_root / "knowledge")
    rag = prepare_purchase_rag(block.config, root, knowledge, documents, block.run_id)
    queries = build_public_queries(inputs, state.get("intake_plan") or {})
    retrieval = retrieve_purchase_rag_context(" ".join(queries), rag, knowledge, documents, max_chars=int((block.config.get("knowledge_rag") or {}).get("max_context_chars", 6000)))
    rag.update({key: retrieval[key] for key in ("context", "citations", "chunks")})
    if retrieval.get("warning"):
        rag.setdefault("warnings", []).append(retrieval["warning"])
    rag.pop("_rag_config", None)
    state.update({"inputs": inputs, "knowledge": knowledge, "rag": rag, "research_queries": queries})
    return {"citation_count": len(rag.get("citations") or []), "state": save_state(block, state, "evidence")}
