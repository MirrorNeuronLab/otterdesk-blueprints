"""Bounded Legal Assistant specialist operations.

These operations own legal-domain extraction and review policy; orchestration,
delivery, and logical-step completion remain with the generated runtime graph.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import WorkflowStateStore

from . import workflow


STATE_FILE = "legal_workflow_state.json"


def _state(ctx: dict[str, Any]) -> dict[str, Any]:
    store = WorkflowStateStore(Path(ctx["run_dir"]))
    state = store.read(STATE_FILE, {})
    state.update(
        {
            "run_id": ctx["run_id"],
            "document_folder": str(
                workflow.expand_runtime_path(
                    ctx["payload"].get("document_folder")
                    or ctx["payload"].get("input_folder")
                    or "examples/sample_inputs"
                )
            ),
            "output_folder": str(ctx["output_folder"]),
        }
    )
    return state


def _save(ctx: dict[str, Any], state: dict[str, Any]) -> None:
    WorkflowStateStore(Path(ctx["run_dir"])).write(STATE_FILE, state)


def watch(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    run_dir = Path(ctx["run_dir"])
    workflow.write_json(run_dir / "run.json", {"run_id": ctx["run_id"], "blueprint_id": workflow.BLUEPRINT_ID, "status": "running", "started_at": workflow.utc_now_iso()})
    workflow.write_json(run_dir / "config.json", ctx["config"])
    workflow.write_json(run_dir / "inputs.json", {"payload": ctx["payload"], "document_folder": state["document_folder"], "dataset_inputs": workflow.DATASET_INPUTS})
    _save(ctx, state)
    return {"document_folder": state["document_folder"]}


def read_documents(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    llm = workflow.build_llm_client(ctx["config"], ctx["payload"], None)
    ocr_client, ocr_status = workflow.build_ocr_runtime({"config": ctx["config"], "payload": ctx["payload"], "llm": llm})
    records = workflow.load_documents(Path(state["document_folder"]), ocr_client=ocr_client)
    state.update({"records": records, "evidence": workflow.summarize_records(records), "warnings": workflow.record_warnings(records), "ocr_status": ocr_status})
    _save(ctx, state)
    return {"document_count": len(records), "warning_count": len(state["warnings"])}


def extract_invoices(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    packet = workflow.extract_invoice_bill_packet(state.get("records") or [])
    state["invoice_packet"] = packet
    _save(ctx, state)
    return {"invoice_count": packet.get("invoice_count", 0)}


def validate_payables(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    packet = state.get("invoice_packet") or workflow.extract_invoice_bill_packet(state.get("records") or [])
    missing = workflow.missing_invoice_fields(packet.get("invoices") or [])
    state["invoice_validation"] = {"missing_fields": missing, "valid": not missing}
    _save(ctx, state)
    return {"missing_field_count": len(missing), "valid": not missing}


def extract_contracts(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    packet = workflow.extract_contract_clause_packet(state.get("records") or [])
    state["clause_packet"] = packet
    _save(ctx, state)
    return {"clause_count": packet.get("clause_count", 0)}


def compare_contracts(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    packet = state.get("clause_packet") or workflow.extract_contract_clause_packet(state.get("records") or [])
    clause_types = [str(item.get("clause_type")) for item in packet.get("clauses") or [] if isinstance(item, dict)]
    comparison = workflow.compare_to_playbook(clause_types)
    state["playbook_comparison"] = comparison
    _save(ctx, state)
    return {"comparison": comparison}


def reconcile_evidence(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    issues = workflow.issue_register(
        state.get("records") or [],
        state.get("invoice_packet") or {},
        state.get("clause_packet") or {},
    )
    state["issues"] = issues
    _save(ctx, state)
    return {"issue_count": len(issues)}


def audit_review(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    records = state.get("records") or []
    llm = workflow.build_llm_client(ctx["config"], ctx["payload"], None)
    knowledge = workflow.load_legal_knowledge(Path(ctx["blueprint_dir"]))
    rag = workflow.prepare_legal_rag(ctx["config"], Path(ctx["blueprint_dir"]), knowledge)
    actor_context = {
        "document_count": len(records),
        "invoice_packet": state.get("invoice_packet") or {},
        "clause_packet": state.get("clause_packet") or {},
        "issue_count": len(state.get("issues") or []),
        "evidence": (state.get("evidence") or [])[:8],
        "review_policy": ctx["payload"].get("review_policy") or {},
        "document_ingestion": {"ocr": state.get("ocr_status") or {}, "source_refs": [record.get("filename") for record in records]},
        "knowledge_rag": {"status": rag.get("status"), "warnings": rag.get("warnings") or []},
    }
    state.update({
        "knowledge": knowledge,
        "rag": {key: value for key, value in rag.items() if not str(key).startswith("_")},
        "actor_findings": workflow.run_actor_reviews(ctx["config"], llm, actor_context, knowledge, rag),
    })
    state["llm_usage"] = workflow.llm_usage(llm, state["actor_findings"])
    _save(ctx, state)
    return {"actor_count": len(state["actor_findings"])}


def publish_report(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    records = state.get("records") or []
    invoice_packet = state.get("invoice_packet") or workflow.extract_invoice_bill_packet(records)
    clause_packet = state.get("clause_packet") or workflow.extract_contract_clause_packet(records)
    issues = state.get("issues") or workflow.issue_register(records, invoice_packet, clause_packet)
    warnings = state.get("warnings") or []
    confidence = 0.35 if not records else 0.58 if warnings or issues else 0.78
    status = "needs_input" if not records else "review_ready_with_issues" if warnings or issues else "review_ready"
    source_refs = ["inputs.json", "events.jsonl", "result.json", "invoice_bill_extraction.json", "contract_clause_review.json"]
    source_refs.extend(sorted({str(record.get("filename")) for record in records if record.get("filename")}))
    knowledge = state.get("knowledge") or {}
    rag = state.get("rag") or {}
    final_artifact = {
        "type": workflow.OUTPUT_TYPE,
        "title": f"{workflow.BLUEPRINT_NAME} Review Packet",
        "status": status,
        "executive_summary": f"{workflow.BLUEPRINT_NAME} processed {len(records)} local document record(s), found {invoice_packet['invoice_count']} invoice/bill packet(s), and extracted {clause_packet['clause_count']} contract clause candidate(s).",
        "recommended_action": workflow.RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": state.get("evidence") or [],
        "next_steps": workflow.next_steps(len(issues)),
        "source_refs": source_refs,
        "dataset_inputs": workflow.DATASET_INPUTS,
        "knowledge_reference": {"id": knowledge.get("id"), "path": knowledge.get("path"), "sha256": knowledge.get("sha256"), "rag": rag},
        "field_profile": {"invoice_fields": workflow.INVOICE_FIELDS, "clause_fields": workflow.CLAUSE_FIELDS},
        "document_count": len(records),
        "invoice_bill_extraction": invoice_packet,
        "contract_clause_review": clause_packet,
        "legal_issue_register": issues,
        "review_boundary": {"review_only": True, "blocked_actions": workflow.blocked_actions()},
        "model_profiles_used": workflow.model_profiles_used(ctx["config"], {}),
        "legal_deep_review": {"actors": state.get("actor_findings") or {}, "review_only": True, "rag_status": rag},
        "actor_findings": state.get("actor_findings") or {},
        "llm_usage": state.get("llm_usage") or {},
        "generated_at": workflow.utc_now_iso(),
    }
    action_ledger, artifact_quality, run_health = workflow.write_outputs(
        final_artifact=final_artifact,
        output_folder=Path(ctx["output_folder"]),
        run_dir=Path(ctx["run_dir"]),
        run_id=ctx["run_id"],
    )
    result = {"run_id": ctx["run_id"], "blueprint_id": workflow.BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact, "action_ledger": action_ledger, "artifact_quality": artifact_quality, "run_health": run_health}
    workflow.write_json(Path(ctx["run_dir"]) / "result.json", result)
    workflow.write_json(Path(ctx["run_dir"]) / "final_artifact.json", final_artifact)
    workflow.write_json(Path(ctx["run_dir"]) / "run.json", {"run_id": ctx["run_id"], "blueprint_id": workflow.BLUEPRINT_ID, "status": "completed", "completed_at": workflow.utc_now_iso()})
    _save(ctx, state)
    return result

