from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result
from runtime.runtime import (
    append_financial_tool_research,
    build_runtime_services,
    persist_action_budget_state,
    read_company_records_state,
    read_company_research_ledger,
    read_company_work_queue_state,
    reconcile_research,
    run_step_actor_review,
    step_actor_review_selected,
    write_company_reconciliation_state,
    write_company_research_ledger,
)

def run_research_reconciler_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, "research_reconciler")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="research_reconciler" if need_llm else "")
    action_budget = services["action_budget"]
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        append_financial_tool_research(company, records, ledger, action_budget=action_budget, run_dir=ctx["run_dir"])
        reconciliation = reconcile_research(records, ledger)
        write_company_research_ledger(ctx["run_dir"], company, ledger)
        write_company_reconciliation_state(ctx["run_dir"], company, reconciliation)
        processed_count += 1
    run_step_actor_review(ctx, "research_reconciler", services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
    complete_runtime_step(ctx, "research_reconciler", {"company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, "research_reconciler", processed_company_count=processed_count, skipped_company_count=skipped_count)
