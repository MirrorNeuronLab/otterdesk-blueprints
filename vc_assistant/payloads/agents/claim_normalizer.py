from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result, write_json, write_workflow_state
from runtime.runtime import (
    build_company_work_queue,
    hydrate_cached_company_state,
    load_watch_state,
    processed_and_skipped_company_names,
)

def run_claim_normalizer_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = ctx["state_store"].read_object("company_records.json")
    previous_state = load_watch_state(ctx["output_folder"])
    company_work_queue = build_company_work_queue(company_records, previous_state, force_reprocess=ctx["force_reprocess"])
    company_work_queue = hydrate_cached_company_state(ctx, company_records, company_work_queue)
    write_json(ctx["output_folder"] / "company_work_queue.json", company_work_queue)
    write_json(ctx["run_dir"] / "company_work_queue.json", company_work_queue)
    write_workflow_state(ctx["run_dir"], "company_work_queue.json", company_work_queue)
    processed, skipped = processed_and_skipped_company_names(company_work_queue)
    complete_runtime_step(ctx, "claim_normalizer", {"company_count": len(processed), "skipped_company_count": len(skipped)})
    return step_result(ctx, "claim_normalizer", processed_company_count=len(processed), skipped_company_count=len(skipped))
