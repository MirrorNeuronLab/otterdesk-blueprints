from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from agents.domain import (
    METHOD_SCORER_FUNCTIONS,
    build_fact_table,
    company_worker_count,
    flattened_sources,
    normalized_research_ledger,
)

from ._shared import create_agent_handler


def run_valuation_scorer(
    ctx: dict[str, Any],
    *,
    method: str,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if method not in METHOD_SCORER_FUNCTIONS:
        raise ValueError(f"unknown valuation method: {method}")
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    scorer = METHOD_SCORER_FUNCTIONS[method]

    def score_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        ledger = normalized_research_ledger(
            store.read_entity_object("research_ledgers", company)
        )
        facts = build_fact_table(company, records, flattened_sources(ledger))
        score = scorer(facts)
        store.write_entity(f"method_scores_by_method/{method}", company, score)
        store.write_entity(f"company_fact_tables_by_method/{method}", company, facts)
        return {"company": company, "method": method, "status": score.get("status")}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=score_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: (
                item.get("status") == "unchanged_skipped"
            ),
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    return {
        "method": method,
        "processed_company_count": int(queue_result["processed_count"]),
        "skipped_company_count": int(queue_result["skipped_count"]),
    }


run = create_agent_handler(run_valuation_scorer)
