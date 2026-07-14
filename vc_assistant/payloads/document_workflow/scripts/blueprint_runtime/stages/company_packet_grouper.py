from __future__ import annotations

from .. import runtime as _runtime

globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

def run_company_packet_grouper_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    files = read_workflow_state(ctx["run_dir"], "document_files.json", [])
    files = [item for item in files if isinstance(item, dict)] if isinstance(files, list) else []
    groups = group_document_file_records(ctx["document_folder"], files)
    packets = [
        {
            "company_name": company,
            "company_slug": slugify(company),
            "document_count": len(items),
            "source_refs": [item.get("path") for item in items],
        }
        for company, items in groups.items()
    ]
    write_workflow_state(ctx["run_dir"], "company_packet_groups.json", packets)
    complete_runtime_step(ctx, "company_packet_grouper", {"company_count": len(packets), "document_file_count": len(files)})
    return step_result(ctx, "company_packet_grouper", company_count=len(packets))

