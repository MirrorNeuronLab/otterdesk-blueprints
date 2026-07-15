from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import complete_runtime_step, step_result
from runtime.runtime import (
    _agent_stage_enabled,
    agentic_research_config,
    build_adaptive_research_plan,
    build_runtime_services,
    persist_action_budget_state,
    read_company_agent_trace_state,
    read_company_analysis_state,
    read_company_records_state,
    read_company_research_ledger,
    read_company_work_queue_state,
    run_agentic_research_stage,
    run_step_actor_review,
    step_actor_review_selected,
    write_company_agent_trace_state,
    write_company_analysis_state,
    write_company_research_ledger,
    write_company_research_plan_state,
)

def run_research_planner_step(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
    agentic = agentic_research_config(ctx["config"])
    need_agentic_planner = bool(agentic.get("enabled")) and _agent_stage_enabled(agentic, "research_planner")
    need_llm = need_agentic_planner or step_actor_review_selected(ctx, "research_planner")
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage="research_planner" if need_llm else "")
    knowledge_rag = services.get("knowledge_rag") or {}
    llm = services.get("llm")
    action_budget = services["action_budget"]
    planned_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        plan = build_adaptive_research_plan(company, records, internet)
        write_company_research_plan_state(ctx["run_dir"], company, plan)
        planned_count += 1
        if item.get("status") == "unchanged_skipped":
            analysis = read_company_analysis_state(ctx["run_dir"], company)
            if analysis:
                analysis["research_plan"] = plan
                write_company_analysis_state(ctx["run_dir"], analysis)
            continue
        if need_agentic_planner and llm is not None:
            trace = read_company_agent_trace_state(ctx["run_dir"], company)
            _, planner_sources = run_agentic_research_stage(
                company=company,
                stage="research_planner",
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
                llm=llm,
                agentic=agentic,
                trace=trace,
                knowledge_rag=knowledge_rag,
            )
            ledger = read_company_research_ledger(ctx["run_dir"], company)
            ledger["company_identity_researcher"] = planner_sources + ledger.get("company_identity_researcher", [])
            write_company_research_ledger(ctx["run_dir"], company, ledger)
            write_company_agent_trace_state(ctx["run_dir"], company, trace)
    run_step_actor_review(ctx, "research_planner", services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
    complete_runtime_step(ctx, "research_planner", {"company_count": planned_count})
    return step_result(ctx, "research_planner", company_count=planned_count)
