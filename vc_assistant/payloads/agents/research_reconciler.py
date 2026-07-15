from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from agents.domain import (
    RESEARCH_AGENT_IDS,
    append_financial_tool_research,
    company_worker_count,
    normalized_research_ledger,
    reconcile_research,
)

from ._shared import create_agent_handler


def run_research_reconciler(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    services = ctx["services"]
    action_budget = services["action_budget"]

    def reconcile_company(
        _context: dict[str, Any], item: dict[str, Any]
    ) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        ledger = normalized_research_ledger(
            store.read_entity_object("research_ledgers", company)
        )
        traces = [
            trace
            for trace in store.read_entity_list("agent_tool_traces", company)
            if isinstance(trace, dict)
        ]
        traces.extend(
            trace
            for agent_id in RESEARCH_AGENT_IDS
            for trace in store.read_entity_list(
                f"agent_tool_traces_by_agent/{agent_id}", company
            )
            if isinstance(trace, dict)
        )
        for agent_id in RESEARCH_AGENT_IDS:
            agent_sources = store.read_entity_list(
                f"research_ledgers_by_agent/{agent_id}", company
            )
            if agent_sources:
                ledger[agent_id] = [*ledger.get(agent_id, []), *agent_sources]
        append_financial_tool_research(
            company,
            records,
            ledger,
            action_budget=action_budget,
            run_dir=ctx["run_dir"],
        )
        reconciliation = reconcile_research(records, ledger)
        store.write_entity(
            "research_ledgers", company, normalized_research_ledger(ledger)
        )
        store.write_entity("agent_tool_traces", company, traces)
        store.write_entity("reconciliations", company, reconciliation)
        return {"company": company, "reconciled": True}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=reconcile_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: (
                item.get("status") == "unchanged_skipped"
            ),
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    processed_count = int(queue_result["processed_count"])
    skipped_count = int(queue_result["skipped_count"])
    return {
        "processed_company_count": processed_count,
        "skipped_company_count": skipped_count,
    }


run = create_agent_handler(run_research_reconciler)
