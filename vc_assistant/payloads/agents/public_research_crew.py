from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue
from runtime.runtime import (
    company_worker_count,
    research_company_with_agents,
)


def run_public_research_crew(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    services = ctx["services"]
    agentic = ctx["config"].get("agentic_research") if isinstance(ctx["config"].get("agentic_research"), dict) else {}
    research_config = {
        **ctx["config"],
        "agentic_research": {
            **agentic,
            "agent_ids": [
                str(agent_id)
                for agent_id in (agentic.get("agent_ids") or [])
                if str(agent_id) != "research_planner"
            ],
        },
    }

    def research_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        trace = [
            record
            for record in store.read_entity_list("agent_tool_traces", company)
            if isinstance(record, dict)
        ]
        ledger = research_company_with_agents(
            company,
            research_config,
            run_dir=ctx["run_dir"],
            action_budget=services["action_budget"],
            records=company_records.get(company, []),
            llm=services.get("llm"),
            agent_tool_trace=trace,
            knowledge_rag=services.get("knowledge_rag") or {},
        )
        store.write_entity("research_ledgers", company, ledger)
        store.write_entity("agent_tool_traces", company, trace)
        return {
            "company": company,
            "research_agent_count": len(ledger),
            "source_count": sum(len(sources) for sources in ledger.values()),
        }

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=research_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: item.get("status") == "unchanged_skipped",
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    return {
        "processed_company_count": int(queue_result["processed_count"]),
        "skipped_company_count": int(queue_result["skipped_count"]),
    }
