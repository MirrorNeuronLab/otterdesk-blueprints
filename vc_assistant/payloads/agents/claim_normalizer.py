from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import slugify, write_json, write_workflow_state
from domain.composition import hydrate_cached_company_state
from domain.evidence import build_company_evidence_layer
from domain.intake import (
    build_company_work_queue,
    load_watch_state,
    processed_and_skipped_company_names,
)

from ._shared import agent_output, create_agent_handler, durable_artifact, input_artifact


def run_claim_normalizer(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    upstream = input_artifact(ctx, "company_records")
    if upstream is not None and upstream.get("path") != "workflow_state/company_records.json":
        raise ValueError("unexpected company records artifact path")
    company_records = ctx["state_store"].read_object("company_records.json")
    previous_state = load_watch_state(ctx["output_folder"])
    company_work_queue = build_company_work_queue(
        company_records, previous_state, force_reprocess=ctx["force_reprocess"]
    )
    company_work_queue = hydrate_cached_company_state(
        ctx, company_records, company_work_queue
    )
    write_json(ctx["output_folder"] / "company_work_queue.json", company_work_queue)
    write_json(ctx["run_dir"] / "company_work_queue.json", company_work_queue)
    write_workflow_state(ctx["run_dir"], "company_work_queue.json", company_work_queue)
    evidence_refs = []
    normalized_claim_count = 0
    for company, records in sorted(company_records.items(), key=lambda item: slugify(item[0])):
        layer = build_company_evidence_layer(company, records, [])
        ctx["state_store"].write_entity("company_evidence", company, layer)
        normalized_claim_count += len(layer.get("claim_records") or [])
        evidence_refs.append(
            durable_artifact(
                "company_evidence",
                f"workflow_state/company_evidence/{slugify(company)}.json",
                company=company,
            )
        )
    write_workflow_state(
        ctx["run_dir"], "company_evidence_index.json", evidence_refs
    )
    processed, skipped = processed_and_skipped_company_names(company_work_queue)
    queue_artifact = durable_artifact(
        "company_work_queue", "workflow_state/company_work_queue.json"
    )
    evidence_index = durable_artifact(
        "company_evidence_index", "workflow_state/company_evidence_index.json"
    )
    return agent_output(
        {
            "processed_company_count": len(processed),
            "skipped_company_count": len(skipped),
            "normalized_claim_count": normalized_claim_count,
            "company_work_queue_artifact": queue_artifact,
            "company_evidence_artifact": evidence_index,
        },
        queue_artifact,
        evidence_index,
        *evidence_refs,
        metrics={"normalized_claim_count": normalized_claim_count},
    )


run = create_agent_handler(run_claim_normalizer)
