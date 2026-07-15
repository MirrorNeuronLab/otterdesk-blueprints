from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from . import domain
from ._shared import create_agent_handler


def run_public_researcher(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    agent_id = str(ctx["agent_id"])
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    services = ctx["services"]
    internet = (
        ctx["config"].get("internet_research")
        if isinstance(ctx["config"].get("internet_research"), dict)
        else {}
    )
    agentic = domain.agentic_research_config(ctx["config"])

    def research_company(
        _context: dict[str, Any], item: dict[str, Any]
    ) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        plan = store.read_entity_object("research_plans", company)
        if not plan:
            plan = domain.build_adaptive_research_plan(company, records, internet)
        query = (plan.get("agent_queries") or {}).get(agent_id, [])
        trace: list[dict[str, Any]] = []
        if internet.get("enabled") is False:
            sources: list[dict[str, Any]] = []
        elif services.get("llm") is not None and domain._research_agent_enabled(
            agentic, agent_id
        ):
            _, sources = domain.run_agentic_research_agent(
                company=company,
                agent_id=agent_id,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=services["action_budget"],
                llm=services["llm"],
                agentic=agentic,
                trace=trace,
                knowledge_rag=services.get("knowledge_rag") or {},
            )
            _, sources = domain._with_agentic_gap_fill(
                company=company,
                agent_id=agent_id,
                sources=sources,
                query=query,
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=services["action_budget"],
            )
        else:
            _, sources = domain._run_research_agent(
                company,
                agent_id,
                query,
                plan,
                internet,
                ctx["run_dir"],
                services["action_budget"],
            )
        store.write_entity(f"research_ledgers_by_agent/{agent_id}", company, sources)
        store.write_entity(f"agent_tool_traces_by_agent/{agent_id}", company, trace)
        return {"company": company, "agent_id": agent_id, "source_count": len(sources)}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=research_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: (
                item.get("status") == "unchanged_skipped"
            ),
            max_workers=lambda _context, **_options: domain.company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    return {
        "agent_id": agent_id,
        "processed_company_count": int(queue_result["processed_count"]),
        "skipped_company_count": int(queue_result["skipped_count"]),
    }


run = create_agent_handler(run_public_researcher)
