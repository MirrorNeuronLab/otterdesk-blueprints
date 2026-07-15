from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result, write_json
from runtime.runtime import (
    METHOD_IDS,
    agentic_research_config,
    build_company_analysis_from_method_scores,
    build_runtime_services,
    company_state_path,
    persist_action_budget_state,
    public_knowledge_rag_state,
    read_company_agent_trace_state,
    read_company_method_scores_state,
    read_company_reconciliation_state,
    read_company_records_state,
    read_company_research_ledger,
    read_company_research_plan_state,
    read_company_work_queue_state,
    reconcile_research,
    run_step_actor_review,
    scoring_fund_profile,
    step_actor_review_selected,
    write_company_analysis_state,
)

def run_score_consistency_auditor_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    need_llm = step_actor_review_selected(ctx, "score_consistency_auditor")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="score_consistency_auditor" if need_llm else "")
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            continue
        records = company_records.get(company, [])
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        methods = read_company_method_scores_state(ctx["run_dir"], company)
        missing_methods = [method_id for method_id in METHOD_IDS if method_id not in methods]
        if missing_methods:
            raise RuntimeError(f"Missing method scores for {company}: {', '.join(missing_methods)}")
        analysis = build_company_analysis_from_method_scores(
            company,
            records,
            ledger,
            methods,
            fund_profile=scoring_fund_profile(ctx["config"]),
        )
        analysis["processing_status"] = "new_or_changed"
        analysis["cached_from_previous_run"] = False
        analysis["cache_policy"] = {
            **(item.get("cache_policy") or {}),
            "cache_source": "",
            "decision": "process_company_packet",
        }
        analysis["research_reconciliation"] = read_company_reconciliation_state(ctx["run_dir"], company) or reconcile_research(records, ledger)
        analysis["research_plan"] = read_company_research_plan_state(ctx["run_dir"], company)
        analysis["agent_tool_trace"] = read_company_agent_trace_state(ctx["run_dir"], company)
        analysis.setdefault("research_plan", {})["knowledge_rag"] = public_knowledge_rag_state(services.get("knowledge_rag") or {})
        analysis["research_plan"]["agentic_research"] = {
            "enabled": bool(agentic_research_config(ctx["config"]).get("enabled")),
            "agent_ids": agentic_research_config(ctx["config"]).get("agent_ids"),
            "allowed_tools": agentic_research_config(ctx["config"]).get("allowed_tools"),
            "max_iterations_per_agent": agentic_research_config(ctx["config"]).get("max_iterations_per_agent"),
            "max_tool_calls_per_agent": agentic_research_config(ctx["config"]).get("max_tool_calls_per_agent"),
            "stop_reasons": {trace.get("agent_id"): trace.get("stop_reason") for trace in analysis["agent_tool_trace"]},
        }
        write_company_analysis_state(ctx["run_dir"], analysis)
        write_json(company_state_path(ctx["run_dir"], "audit_findings", company), analysis["audit"])
        processed_count += 1
    run_step_actor_review(ctx, "score_consistency_auditor", services, llm_client=llm_client)
    persist_action_budget_state(ctx, services["action_budget"])
    complete_runtime_step(ctx, "score_consistency_auditor", {"company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, "score_consistency_auditor", processed_company_count=processed_count, skipped_company_count=skipped_count)
