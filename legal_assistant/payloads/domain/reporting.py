"""Customer-facing legal packet composition and artifact publication."""

from __future__ import annotations

from .common import *
from .contracts import extract_contract_clause_packet
from .invoices import extract_invoice_bill_packet
from .knowledge import load_legal_knowledge
from .review import issue_register, model_profiles_used
from .state import load_state, save_state

def next_steps(issue_count: int) -> list[str]:
    steps = [
        "Review invoice amounts, due dates, supplier details, and contract clauses against the source files.",
        "Ask an attorney to confirm clause classifications, missing terms, privilege concerns, and playbook deviations.",
        "Approve, revise, or reject the packet before any payment, ERP, signature, counterparty, or external-sharing action.",
    ]
    if issue_count:
        steps.insert(0, f"Resolve {issue_count} issue-register item(s) before downstream use.")
    return steps

def blocked_actions() -> list[str]:
    return list(BLOCKED_ACTIONS)

def build_markdown(final_artifact: dict[str, Any]) -> str:
    lines = [
        "# Legal Assistant Report",
        "",
        f"**Status:** {final_artifact.get('status')}",
        f"**Recommended action:** {final_artifact.get('recommended_action')}",
        f"**Confidence:** {final_artifact.get('confidence')}",
        "",
        "## Executive Summary",
        str(final_artifact.get("executive_summary") or ""),
        "",
        "## Invoice And Bill Review",
    ]
    invoice_packet = final_artifact.get("invoice_bill_extraction") or {}
    lines.append(f"- Invoices or bills detected: {invoice_packet.get('invoice_count', 0)}")
    lines.append(f"- Total extracted amount: {invoice_packet.get('totals', {}).get('total_amount', 0)}")
    for invoice in invoice_packet.get("invoices") or []:
        lines.append(f"- {invoice.get('source')}: {invoice.get('supplier_name') or 'Unknown supplier'} / {invoice.get('total_amount')}")
    lines.extend(["", "## Contract Clause Review"])
    clause_packet = final_artifact.get("contract_clause_review") or {}
    lines.append(f"- Contracts detected: {clause_packet.get('contract_count', 0)}")
    lines.append(f"- Clauses detected: {clause_packet.get('clause_count', 0)}")
    for clause in (clause_packet.get("clauses") or [])[:10]:
        lines.append(f"- {clause.get('clause_type')}: {clause.get('source')}")
    lines.extend(["", "## Issue Register"])
    for issue in final_artifact.get("legal_issue_register") or []:
        lines.append(f"- [{issue.get('severity')}] {issue.get('area')}: {issue.get('issue')}")
    ingestion = final_artifact.get("document_ingestion") or {}
    rag = (final_artifact.get("knowledge_reference") or {}).get("rag") or {}
    lines.extend(
        [
            "",
            "## OCR And RAG",
            f"- OCR status: {(ingestion.get('ocr') or {}).get('status', 'not reported')}",
            f"- OCR runtime model: {(ingestion.get('ocr') or {}).get('runtime_model') or 'selected automatically by the OCR skill'}",
            f"- OCR-required sources: {', '.join(ingestion.get('ocr_required_sources') or ['none'])}",
            f"- Knowledge RAG status: {rag.get('status', 'not reported')}",
            f"- Knowledge RAG warnings: {len(rag.get('warnings') or [])}",
        ]
    )
    lines.extend(["", "## Deep LLM Review"])
    for actor_id, finding in (final_artifact.get("actor_findings") or {}).items():
        if not isinstance(finding, dict):
            continue
        lines.extend(
            [
                f"### {finding.get('role') or actor_id}",
                str(finding.get("summary") or "No LLM summary returned."),
                f"- Findings: {'; '.join(str(item) for item in (finding.get('key_findings') or finding.get('findings') or [])[:5]) or 'none'}",
                f"- Review questions: {'; '.join(str(item) for item in (finding.get('review_questions') or [])[:5]) or 'none'}",
                f"- Evidence gaps: {'; '.join(str(item) for item in (finding.get('evidence_gaps') or [])[:5]) or 'none'}",
                f"- Risk flags: {'; '.join(str(item) for item in (finding.get('risk_flags') or [])[:5]) or 'none'}",
                f"- Confidence: {finding.get('confidence')}",
                f"- Source refs: {', '.join(str(item) for item in (finding.get('source_refs') or [])[:8]) or 'none'}",
                "",
            ]
        )
    lines.extend(["", "## Evidence Highlights"])
    for item in (final_artifact.get("evidence") or [])[:10]:
        preview = str(item.get("text_preview") or "").replace("\n", " ").strip()
        if len(preview) > 220:
            preview = preview[:217] + "..."
        lines.append(f"- **{item.get('source')}** ({item.get('document_type')}): {preview or 'No text preview available.'}")
    lines.extend(["", "## Review Boundary"])
    for action in blocked_actions():
        lines.append(f"- {action}")
    lines.extend(["", "## Source References"])
    for ref in final_artifact.get("source_refs") or []:
        lines.append(f"- `{ref}`")
    return "\n".join(lines) + "\n"

def write_outputs(
    *,
    final_artifact: dict[str, Any],
    output_folder: Path,
    run_dir: Path,
    run_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    output_folder.mkdir(parents=True, exist_ok=True)
    warnings = final_artifact.get("quality_summary", {}).get("warnings") or []
    action_ledger = {
        "schema_version": "mn.blueprint.action_ledger.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "review_only": True,
        "actions": [
            {"step": "load_inputs", "status": "completed", "source_refs": ["inputs.json"]},
            {"step": "extract_invoice_bill_fields", "status": "completed"},
            {"step": "extract_contract_clauses", "status": "completed"},
            {"step": "write_integrated_report", "status": "completed", "output_folder": str(output_folder)},
        ],
        "blocked_actions": blocked_actions(),
    }
    artifact_quality = {
        "schema_version": "mn.blueprint.artifact_quality.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "usable_with_review" if final_artifact.get("document_count") else "needs_input",
        "checks": [
            {"name": "has_evidence", "ok": bool(final_artifact.get("evidence"))},
            {"name": "has_invoice_or_contract_artifact", "ok": bool(final_artifact.get("invoice_bill_extraction") or final_artifact.get("contract_clause_review"))},
            {"name": "review_boundary_present", "ok": True},
            {"name": "deep_llm_review_present", "ok": bool(final_artifact.get("legal_deep_review", {}).get("actors"))},
            {"name": "writes_user_download_folder", "ok": True},
        ],
        "warning_count": len(warnings),
        "warnings": warnings[:20],
        "issue_count": len(final_artifact.get("legal_issue_register") or []),
    }
    run_health = {
        "schema_version": "mn.blueprint.run_health.v1",
        "blueprint_id": BLUEPRINT_ID,
        "run_id": run_id,
        "status": "completed",
        "warning_count": len(warnings),
        "failure_count": 0,
        "output_folder": str(output_folder),
        "run_store": str(run_dir),
        "llm_provider": (final_artifact.get("llm_usage") or {}).get("provider"),
        "llm_model": (final_artifact.get("llm_usage") or {}).get("model"),
        "llm_calls": (final_artifact.get("llm_usage") or {}).get("calls"),
        "ocr_status": ((final_artifact.get("document_ingestion") or {}).get("ocr") or {}).get("status"),
        "rag_status": ((final_artifact.get("knowledge_reference") or {}).get("rag") or {}).get("status"),
        "generated_at": utc_now_iso(),
    }
    write_json(output_folder / "final_artifact.json", final_artifact)
    write_json(output_folder / "invoice_bill_extraction.json", final_artifact["invoice_bill_extraction"])
    write_json(output_folder / "contract_clause_review.json", final_artifact["contract_clause_review"])
    write_json(output_folder / "legal_issue_register.json", final_artifact["legal_issue_register"])
    write_json(output_folder / "legal_deep_review.json", final_artifact["legal_deep_review"])
    write_json(output_folder / "action_ledger.json", action_ledger)
    write_json(output_folder / "artifact_quality.json", artifact_quality)
    write_json(output_folder / "run_health.json", run_health)
    write_text(output_folder / "legal_assistant_report.md", build_markdown(final_artifact))
    for name, value in (
        ("action_ledger.json", action_ledger),
        ("artifact_quality.json", artifact_quality),
        ("run_health.json", run_health),
    ):
        write_json(run_dir / name, value)
    write_json(run_dir / "legal_deep_review.json", final_artifact["legal_deep_review"])
    return action_ledger, artifact_quality, run_health


def publish_report(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = load_state(ctx)
    records = state.get("records") or []
    invoice_packet = state.get("invoice_packet") or extract_invoice_bill_packet(records)
    clause_packet = state.get("clause_packet") or extract_contract_clause_packet(records)
    issues = state.get("issues") or issue_register(records, invoice_packet, clause_packet)
    warnings = state.get("warnings") or []
    confidence = 0.35 if not records else 0.58 if warnings or issues else 0.78
    status = "needs_input" if not records else "review_ready_with_issues" if warnings or issues else "review_ready"
    source_refs = ["inputs.json", "events.jsonl", "result.json", "invoice_bill_extraction.json", "contract_clause_review.json"]
    source_refs.extend(sorted({str(record.get("filename")) for record in records if record.get("filename")}))
    knowledge = state.get("knowledge") or load_legal_knowledge(Path(ctx["blueprint_dir"]))
    rag = state.get("rag") or {}
    obligation_calendar = [{
        "obligation": "Review invoice before payment approval",
        "date": invoice.get("due_date") or "unknown",
        "source_ref": invoice.get("source"),
        "owner": "accounts_payable_reviewer",
        "status": "pending_human_review",
    } for invoice in invoice_packet.get("invoices") or []]
    obligation_calendar.extend({
        "obligation": f"Review {clause.get('clause_type')} clause and related notice or survival terms",
        "date": "not_extracted",
        "source_ref": clause.get("source_ref") or clause.get("source"),
        "locator": clause.get("locator"),
        "owner": "attorney",
        "status": "pending_human_review",
    } for clause in clause_packet.get("clauses") or [] if clause.get("clause_type") in {"termination", "renewal", "assignment", "indemnity", "liability"})
    review_queue = sorted(issues, key=lambda item: ({"high": 0, "medium": 1, "low": 2}.get(str(item.get("severity") or "low"), 3), str(item.get("area") or ""), str(item.get("source") or "")))
    final_artifact = {
        "type": OUTPUT_TYPE,
        "title": f"{BLUEPRINT_NAME} Review Packet",
        "status": status,
        "executive_summary": f"{BLUEPRINT_NAME} processed {len(records)} local document record(s), found {invoice_packet['invoice_count']} invoice/bill packet(s), and extracted {clause_packet['clause_count']} contract clause candidate(s).",
        "recommended_action": RECOMMENDED_ACTION,
        "confidence": confidence,
        "evidence": state.get("evidence") or [],
        "next_steps": next_steps(len(issues)),
        "source_refs": source_refs,
        "dataset_inputs": DATASET_INPUTS,
        "knowledge_reference": {"id": knowledge.get("id"), "path": knowledge.get("path"), "sha256": knowledge.get("sha256"), "rag": rag},
        "field_profile": {"invoice_fields": INVOICE_FIELDS, "clause_fields": CLAUSE_FIELDS},
        "document_count": len(records),
        "document_summary": {
            "document_count": len(records),
            "invoice_or_bill_count": invoice_packet.get("invoice_count", 0),
            "contract_or_clause_count": clause_packet.get("contract_count", 0),
            "ocr_required_count": sum(1 for record in records if record.get("ocr_required")),
            "warning_count": len(warnings),
            "document_types": sorted({str(record.get("document_type")) for record in records}),
        },
        "document_ingestion": {"ocr": state.get("ocr_status") or {}, "ocr_required_sources": [record.get("filename") for record in records if record.get("ocr_required")]},
        "invoice_bill_extraction": invoice_packet,
        "contract_clause_review": clause_packet,
        "legal_issue_register": issues,
        "priority_review_queue": review_queue,
        "obligation_calendar": obligation_calendar,
        "matter_overview": {
            "document_count": len(records),
            "invoice_count": invoice_packet.get("invoice_count", 0),
            "contract_count": clause_packet.get("contract_count", 0),
            "high_severity_issue_count": sum(1 for item in issues if item.get("severity") == "high"),
            "open_obligation_count": len(obligation_calendar),
        },
        "quality_summary": {"real_values_present": bool(records), "evidence_preview_count": len(state.get("evidence") or []), "warnings": warnings[:10], "issue_count": len(issues)},
        "review_boundary": {"review_only": True, "blocked_actions": blocked_actions()},
        "model_profiles_used": model_profiles_used(ctx["config"], {}),
        "legal_deep_review": {"actors": state.get("actor_findings") or {}, "review_only": True, "rag_status": rag},
        "actor_findings": state.get("actor_findings") or {},
        "llm_usage": state.get("llm_usage") or {},
        "generated_at": utc_now_iso(),
    }
    action_ledger, artifact_quality, run_health = write_outputs(final_artifact=final_artifact, output_folder=Path(ctx["output_folder"]), run_dir=Path(ctx["run_dir"]), run_id=ctx["run_id"])
    result = {"run_id": ctx["run_id"], "blueprint_id": BLUEPRINT_ID, "status": "completed", "final_artifact": final_artifact, "action_ledger": action_ledger, "artifact_quality": artifact_quality, "run_health": run_health}
    write_json(Path(ctx["run_dir"]) / "result.json", result)
    write_json(Path(ctx["run_dir"]) / "final_artifact.json", final_artifact)
    save_state(ctx, state, "legal_review_state.json")
    return result


__all__ = ["publish_report"]
