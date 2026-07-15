from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import write_failed_run, write_workflow_state
from agents.domain import (
    OcrRequiredError,
    SUPPORTED_SUFFIXES,
    append_event,
    observed_operation,
    scan_documents,
    stable_text_hash,
)

from ._shared import create_agent_handler


def run_document_evidence_extractor(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    try:
        with observed_operation(
            ctx["run_dir"],
            phase="document_evidence_extractor",
            operation="scan_documents",
            path_hash=stable_text_hash(ctx["document_folder"]),
            supported_suffixes=sorted(SUPPORTED_SUFFIXES),
        ) as op:
            company_records = scan_documents(ctx["document_folder"], ctx["config"])
            if not company_records:
                company_records = {"Sample Startup": []}
            op.close(
                "completed",
                company_count=len(company_records),
                document_count=sum(
                    len(records) for records in company_records.values()
                ),
            )
    except OcrRequiredError as exc:
        append_event(
            ctx["run_dir"],
            "tool_call_failed",
            {
                "tool": "llm_ocr.extract_document_folder",
                "status": "required_ocr_failed",
                "error": str(exc),
            },
        )
        write_failed_run(ctx, exc)
        raise
    write_workflow_state(ctx["run_dir"], "company_records.json", company_records)
    return {
        "company_count": len(company_records),
        "document_count": sum(len(records) for records in company_records.values()),
    }


run = create_agent_handler(run_document_evidence_extractor)
