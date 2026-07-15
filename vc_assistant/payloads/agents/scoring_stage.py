from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result, write_json
from runtime.runtime import (
    METHOD_SCORER_FUNCTIONS,
    SCORER_METHOD_BY_STAGE,
    build_fact_table,
    build_runtime_services,
    company_state_path,
    flattened_sources,
    persist_action_budget_state,
    read_company_records_state,
    read_company_research_ledger,
    read_company_work_queue_state,
    run_step_actor_review,
    step_actor_review_selected,
    write_company_method_score_state,
)

def run_scorer_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    method_id = SCORER_METHOD_BY_STAGE[step_id]
    scorer = METHOD_SCORER_FUNCTIONS[method_id]
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, step_id)
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage=step_id if need_llm else "")
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        facts = build_fact_table(company, records, flattened_sources(ledger))
        write_company_method_score_state(ctx["run_dir"], company, method_id, scorer(facts))
        write_json(company_state_path(ctx["run_dir"], "company_fact_tables", company), facts)
        processed_count += 1
    run_step_actor_review(ctx, step_id, services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, step_id, {"method_id": method_id, "company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, step_id, method_id=method_id, processed_company_count=processed_count, skipped_company_count=skipped_count)
