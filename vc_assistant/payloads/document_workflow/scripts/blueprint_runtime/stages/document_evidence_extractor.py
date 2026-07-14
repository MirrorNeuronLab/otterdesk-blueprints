from __future__ import annotations

from .. import runtime as _runtime

globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

def run_document_evidence_extractor_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    try:
        with observed_operation(ctx["run_dir"], phase="document_evidence_extractor", operation="scan_documents", path_hash=stable_text_hash(ctx["document_folder"]), supported_suffixes=sorted(SUPPORTED_SUFFIXES)) as op:
            company_records = _runtime.scan_documents(ctx["document_folder"], ctx["config"])
            if not company_records:
                company_records = {"Sample Startup": []}
            op.close("completed", company_count=len(company_records), document_count=sum(len(records) for records in company_records.values()))
    except OcrRequiredError as exc:
        append_event(ctx["run_dir"], "tool_call_failed", {"tool": "llm_ocr.extract_document_folder", "status": "required_ocr_failed", "error": str(exc)})
        write_failed_run(ctx, exc)
        raise
    write_workflow_state(ctx["run_dir"], "company_records.json", company_records)
    complete_runtime_step(
        ctx,
        "document_evidence_extractor",
        {"company_count": len(company_records), "document_count": sum(len(records) for records in company_records.values())},
    )
    return step_result(ctx, "document_evidence_extractor", company_count=len(company_records))
