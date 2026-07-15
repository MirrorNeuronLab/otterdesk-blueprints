from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue
from mn_public_research_orchestrator_skill import merge_stage_sources
from mn_sdk.blueprint_support import complete_runtime_step, step_result
from runtime.runtime import (
    _agent_stage_enabled,
    _research_one_stage,
    _with_agentic_gap_fill,
    agentic_research_config,
    append_debug_record_if_enabled,
    build_adaptive_research_plan,
    company_worker_count,
    fake_llm_mode_enabled,
    fake_skills_mode_enabled,
    normalized_research_ledger,
    run_agentic_research_stage,
)

def run_research_stage_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
    internet_disabled = internet.get("enabled") is False
    agentic = agentic_research_config(ctx["config"])
    need_agentic = bool(agentic.get("enabled")) and _agent_stage_enabled(agentic, step_id)
    services = ctx["services"]
    llm = services.get("llm")
    need_llm = llm is not None
    append_debug_record_if_enabled(
        ctx,
        "debug_research_stage_started",
        {
            "step_id": step_id,
            "company_queue_count": len(company_work_queue),
            "company_record_count": len(company_records),
            "internet_disabled": internet_disabled,
            "need_agentic": need_agentic,
            "need_llm": need_llm,
            "agentic_enabled": bool(agentic.get("enabled")),
            "fake_llm": fake_llm_mode_enabled(ctx["config"]),
            "fake_skills": fake_skills_mode_enabled(ctx["config"]),
        },
    )
    knowledge_rag = services.get("knowledge_rag") or {}
    action_budget = services["action_budget"]
    def process_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        if internet_disabled:
            ledger = normalized_research_ledger(store.read_entity_object("research_ledgers", company))
            ledger.setdefault(step_id, [])
            store.write_entity("research_ledgers", company, normalized_research_ledger(ledger))
            append_debug_record_if_enabled(
                ctx,
                "debug_research_company_completed",
                {
                    "step_id": step_id,
                    "company": company,
                    "internet_disabled": True,
                    "source_count": 0,
                    "ledger_stage_count": len(ledger.get(step_id, [])),
                },
            )
            return {"company": company, "source_count": 0}
        records = company_records.get(company, [])
        plan = store.read_entity_object("research_plans", company) or build_adaptive_research_plan(company, records, internet)
        staged_queries = plan.get("stage_queries") if isinstance(plan.get("stage_queries"), dict) else {}
        query = staged_queries.get(step_id) or plan.get("queries") or [company]
        trace = [
            item
            for item in store.read_entity_list("agent_tool_traces", company)
            if isinstance(item, dict)
        ]
        append_debug_record_if_enabled(
            ctx,
            "debug_research_company_started",
            {
                "step_id": step_id,
                "company": company,
                "record_count": len(records),
                "query_count": len(query) if isinstance(query, list) else 1,
                "existing_trace_count": len(trace),
                "agentic": need_agentic and llm is not None,
            },
        )
        if need_agentic and llm is not None:
            stage, sources = run_agentic_research_stage(
                company=company,
                stage=step_id,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
                llm=llm,
                agentic=agentic,
                trace=trace,
                knowledge_rag=knowledge_rag,
            )
            stage, sources = _with_agentic_gap_fill(
                company=company,
                stage=stage,
                sources=sources,
                query=query,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
            )
        else:
            stage, sources = _research_one_stage(
                company,
                step_id,
                query,
                plan,
                internet,
                ctx["run_dir"],
                action_budget,
            )
        ledger = normalized_research_ledger(store.read_entity_object("research_ledgers", company))
        ledger = merge_stage_sources(ledger, stage, sources, deduplicate=False)
        store.write_entity("research_ledgers", company, normalized_research_ledger(ledger))
        store.write_entity("agent_tool_traces", company, trace)
        append_debug_record_if_enabled(
            ctx,
            "debug_research_company_completed",
            {
                "step_id": step_id,
                "company": company,
                "stage": stage,
                "source_count": len(sources),
                "ledger_stage_count": len(ledger.get(stage, [])),
                "trace_count": len(trace),
                "action_budget_class": action_budget.__class__.__name__,
            },
        )
        return {"company": company, "source_count": len(sources), "stage": stage}

    def should_skip(_context: dict[str, Any], item: dict[str, Any], **_options: Any) -> bool:
        skipped = item.get("status") == "unchanged_skipped"
        if skipped:
            append_debug_record_if_enabled(
                ctx,
                "debug_research_company_skipped",
                {"step_id": step_id, "company": str(item["company_name"]), "status": item.get("status")},
            )
        return skipped

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=process_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=should_skip,
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    processed_count = int(queue_result["processed_count"])
    skipped_count = int(queue_result["skipped_count"])
    complete_runtime_step(ctx, step_id, {"company_count": processed_count, "skipped_company_count": skipped_count})
    append_debug_record_if_enabled(
        ctx,
        "debug_research_stage_completed",
        {
            "step_id": step_id,
            "processed_company_count": processed_count,
            "skipped_company_count": skipped_count,
        },
    )
    return step_result(ctx, step_id, processed_company_count=processed_count, skipped_company_count=skipped_count)
