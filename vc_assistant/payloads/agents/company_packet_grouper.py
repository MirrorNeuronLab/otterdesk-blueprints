from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import (
    read_workflow_state,
    slugify,
    write_workflow_state,
)
from domain.intake import group_document_file_records

from ._shared import agent_output, create_agent_handler, durable_artifact, input_artifact


def run_company_packet_grouper(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    upstream = input_artifact(ctx, "document_file_index")
    if upstream is not None and upstream.get("path") != "workflow_state/document_files.json":
        raise ValueError("unexpected document file index artifact path")
    files = read_workflow_state(ctx["run_dir"], "document_files.json", [])
    files = (
        [item for item in files if isinstance(item, dict)]
        if isinstance(files, list)
        else []
    )
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
    artifact = durable_artifact(
        "company_packet_index", "workflow_state/company_packet_groups.json"
    )
    return agent_output(
        {
            "company_count": len(packets),
            "document_file_count": len(files),
            "company_packets_artifact": artifact,
        },
        artifact,
        metrics={"company_count": len(packets)},
    )


run = create_agent_handler(run_company_packet_grouper)
