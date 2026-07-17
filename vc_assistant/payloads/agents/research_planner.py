from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import write_workflow_state
from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from domain.execution_policy import company_worker_count
from domain.research_agentic import run_agentic_research_agent
from domain.research_core import (
    _research_agent_enabled,
    agentic_research_config,
    normalized_research_ledger,
)
from domain.research_policy import build_adaptive_research_plan

from ._shared import agent_output, create_agent_handler, durable_artifact, input_artifact


def run_research_planner(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    input_artifact(ctx, "company_evidence_index")
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    internet = (
        ctx["config"].get("internet_research")
        if isinstance(ctx["config"].get("internet_research"), dict)
        else {}
    )
    agentic = agentic_research_config(ctx["config"])
    need_agentic_planner = bool(agentic.get("enabled")) and _research_agent_enabled(
        agentic, "research_planner"
    )
    services = ctx["services"]
    knowledge_rag = services.get("knowledge_rag") or {}
    llm = services.get("llm")
    action_budget = services["action_budget"]

    def plan_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        plan = build_adaptive_research_plan(company, records, internet)
        store.write_entity("research_plans", company, plan)
        if item.get("status") == "unchanged_skipped":
            analysis = store.read_entity_object("analyses", company)
            if analysis:
                analysis["research_plan"] = plan
                store.write_entity("analyses", str(analysis["company_slug"]), analysis)
        elif need_agentic_planner and llm is not None:
            trace = [
                item
                for item in store.read_entity_list("agent_tool_traces", company)
                if isinstance(item, dict)
            ]
            _, planner_sources = run_agentic_research_agent(
                company=company,
                agent_id="research_planner",
                plan=plan,
                internet=internet,
                run_dir=ctx["run_dir"],
                action_budget=action_budget,
                llm=llm,
                agentic=agentic,
                trace=trace,
                knowledge_rag=knowledge_rag,
            )
            ledger = normalized_research_ledger(
                store.read_entity_object("research_ledgers", company)
            )
            ledger["company_identity_researcher"] = planner_sources + ledger.get(
                "company_identity_researcher", []
            )
            store.write_entity(
                "research_ledgers", company, normalized_research_ledger(ledger)
            )
            store.write_entity("agent_tool_traces", company, trace)
        return {"company": company, "planned": True}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=plan_company,
            entity_id=lambda item: str(item["company_name"]),
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    planned_count = int(queue_result["processed_count"])
    refs = [
        durable_artifact(
            "research_plan",
            f"workflow_state/research_plans/{item['company_slug']}.json",
            company=item["company_name"],
        )
        for item in company_work_queue
    ]
    write_workflow_state(ctx["run_dir"], "research_plan_index.json", refs)
    index = durable_artifact(
        "research_plan_index", "workflow_state/research_plan_index.json"
    )
    return agent_output(
        {"company_count": planned_count, "research_plan_artifact": index},
        index,
        *refs,
        metrics={"company_count": planned_count},
    )


run = create_agent_handler(run_research_planner)
