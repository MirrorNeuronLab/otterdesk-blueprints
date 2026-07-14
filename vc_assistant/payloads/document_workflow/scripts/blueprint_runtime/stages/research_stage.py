from __future__ import annotations

from .. import runtime as _runtime

globals().update({name: value for name, value in vars(_runtime).items() if not name.startswith("__")})

def run_research_stage_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    company_records = read_company_records_state(ctx["run_dir"])
    company_work_queue = read_company_work_queue_state(ctx["run_dir"])
    internet = ctx["config"].get("internet_research") if isinstance(ctx["config"].get("internet_research"), dict) else {}
    internet_disabled = internet.get("enabled") is False
    agentic = agentic_research_config(ctx["config"])
    need_agentic = bool(agentic.get("enabled")) and _agent_stage_enabled(agentic, step_id)
    need_llm = need_agentic or step_actor_review_selected(ctx, step_id)
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
    services = build_runtime_services(ctx, llm_client=llm_client, need_llm=need_llm, rag_stage=step_id if need_llm else "")
    llm = services.get("llm")
    knowledge_rag = services.get("knowledge_rag") or {}
    action_budget = services["action_budget"]
    processed_count = 0
    skipped_count = 0
    for item in company_work_queue:
        company = str(item["company_name"])
        if item.get("status") == "unchanged_skipped":
            skipped_count += 1
            append_debug_record_if_enabled(
                ctx,
                "debug_research_company_skipped",
                {"step_id": step_id, "company": company, "status": item.get("status")},
            )
            continue
        if internet_disabled:
            ledger = read_company_research_ledger(ctx["run_dir"], company)
            ledger.setdefault(step_id, [])
            write_company_research_ledger(ctx["run_dir"], company, ledger)
            processed_count += 1
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
            continue
        records = company_records.get(company, [])
        plan = read_company_research_plan_state(ctx["run_dir"], company) or build_adaptive_research_plan(company, records, internet)
        staged_queries = plan.get("stage_queries") if isinstance(plan.get("stage_queries"), dict) else {}
        query = staged_queries.get(step_id) or plan.get("queries") or [company]
        trace = read_company_agent_trace_state(ctx["run_dir"], company)
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
            stage, sources = _runtime._research_one_stage(
                company,
                step_id,
                query,
                plan,
                internet,
                ctx["run_dir"],
                action_budget,
            )
        ledger = read_company_research_ledger(ctx["run_dir"], company)
        ledger[stage] = ledger.get(stage, []) + sources
        write_company_research_ledger(ctx["run_dir"], company, ledger)
        write_company_agent_trace_state(ctx["run_dir"], company, trace)
        processed_count += 1
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
    run_step_actor_review(ctx, step_id, services, llm_client=llm_client)
    persist_action_budget_state(ctx, action_budget)
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
