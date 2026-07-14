from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._state import build_stage_context, result


def run(context: StepContext, operation: str) -> dict[str, Any]:
    ctx = build_stage_context(context)
    state = ctx["state"]
    records = state.get("records") or []
    invoice_packet = state.get("invoice_packet") or runtime.extract_invoice_bill_packet(records)
    clause_packet = state.get("clause_packet") or runtime.extract_contract_clause_packet(records)

    if operation == "reconcile":
        issues = runtime.issue_register(records, invoice_packet, clause_packet)
        state["issues"] = issues
        return result(ctx, issue_count=len(issues))

    if operation == "audit":
        llm = runtime.build_llm_client(ctx["config"], ctx["payload"], None)
        knowledge = runtime.load_legal_knowledge(ctx["root"])
        rag = runtime.prepare_legal_rag(ctx["config"], ctx["root"], knowledge)
        actor_context = {
            "document_count": len(records),
            "invoice_packet": invoice_packet,
            "clause_packet": clause_packet,
            "issue_count": len(state.get("issues") or []),
            "evidence": (state.get("evidence") or [])[:8],
            "review_policy": ctx["payload"].get("review_policy") or {},
            "document_ingestion": {"ocr": state.get("ocr_status") or {}, "source_refs": [record.get("filename") for record in records]},
            "knowledge_rag": {"status": rag.get("status"), "warnings": rag.get("warnings") or []},
        }
        state["knowledge"] = knowledge
        state["rag"] = {key: value for key, value in rag.items() if not str(key).startswith("_")}
        state["actor_findings"] = runtime.run_actor_reviews(ctx["config"], llm, actor_context, knowledge, rag)
        state["llm_usage"] = runtime.llm_usage(llm, state["actor_findings"])
        return result(ctx, actor_count=len(state["actor_findings"]))

    if operation == "report":
        return _write_report(ctx, invoice_packet, clause_packet)

    raise ValueError(f"unknown legal review operation: {operation}")


def _write_report(ctx: dict[str, Any], invoice_packet: dict[str, Any], clause_packet: dict[str, Any]) -> dict[str, Any]:
    state = ctx["state"]
    records = state.get("records") or []
    evidence = state.get("evidence") or []
    issues = state.get("issues") or runtime.issue_register(records, invoice_packet, clause_packet)
    warnings = state.get("warnings") or []
    confidence = 0.35 if not records else 0.58 if warnings or issues else 0.78
    status = "needs_input" if not records else "review_ready_with_issues" if warnings or issues else "review_ready"
    source_refs = ["inputs.json", "events.jsonl", "result.json", "invoice_bill_extraction.json", "contract_clause_review.json"]
    source_refs.extend(sorted({str(record.get("filename")) for record in records if record.get("filename")}))
    knowledge = state.get("knowledge") or {}
    rag = state.get("rag") or {}
    actor_findings = state.get("actor_findings") or {}
    final_artifact = {
        "type": runtime.OUTPUT_TYPE,
        "title": f"{runtime.BLUEPRINT_NAME} Review Packet",
        "status": status,
        "executive_summary": f"{runtime.BLUEPRINT_NAME} processed {len(records)} local document record(s), found {invoice_packet['invoice_count']} invoice/bill packet(s), and extracted {clause_packet['clause_count']} contract clause candidate(s).",
        "recommended_action": runtime.RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": evidence,
        "next_steps": runtime.next_steps(len(issues)),
        "source_refs": source_refs,
        "dataset_inputs": runtime.DATASET_INPUTS,
        "knowledge_reference": {"id": knowledge.get("id"), "path": knowledge.get("path"), "sha256": knowledge.get("sha256"), "rag": rag},
        "field_profile": {"invoice_fields": runtime.INVOICE_FIELDS, "clause_fields": runtime.CLAUSE_FIELDS},
        "document_count": len(records),
        "document_summary": {
            "document_count": len(records),
            "invoice_or_bill_count": len(runtime.invoice_records(records)),
            "contract_or_clause_count": len(runtime.contract_records(records)),
            "ocr_required_count": len([record for record in records if record.get("ocr_required")]),
            "warning_count": len(warnings),
            "document_types": sorted({str(record.get("document_type")) for record in records}),
        },
        "document_ingestion": {"ocr": state.get("ocr_status") or {}, "ocr_required_count": len([record for record in records if record.get("ocr_required")])},
        "invoice_bill_extraction": invoice_packet,
        "contract_clause_review": clause_packet,
        "legal_issue_register": issues,
        "quality_summary": {"real_values_present": bool(records), "evidence_preview_count": len(evidence), "warnings": warnings[:10], "issue_count": len(issues)},
        "review_boundary": {"review_only": True, "blocked_actions": runtime.blocked_actions()},
        "model_profiles_used": runtime.model_profiles_used(ctx["config"], {}),
        "legal_deep_review": {"actors": actor_findings, "review_only": True, "rag_status": rag},
        "actor_findings": actor_findings,
        "llm_usage": state.get("llm_usage") or {},
        "generated_at": runtime.utc_now_iso(),
    }
    action_ledger, artifact_quality, run_health = runtime.write_outputs(
        final_artifact=final_artifact,
        output_folder=ctx["output_folder"],
        run_dir=ctx["run_dir"],
        run_id=ctx["run_id"],
    )
    completed = {
        "run_id": ctx["run_id"],
        "blueprint_id": runtime.BLUEPRINT_ID,
        "status": "completed",
        "records": records,
        "final_artifact": final_artifact,
        "action_ledger": action_ledger,
        "artifact_quality": artifact_quality,
        "run_health": run_health,
    }
    runtime.write_json(ctx["run_dir"] / "result.json", completed)
    runtime.write_json(ctx["run_dir"] / "final_artifact.json", final_artifact)
    runtime.write_json(ctx["run_dir"] / "run.json", {"run_id": ctx["run_id"], "blueprint_id": runtime.BLUEPRINT_ID, "status": "completed", "completed_at": runtime.utc_now_iso()})
    return completed
