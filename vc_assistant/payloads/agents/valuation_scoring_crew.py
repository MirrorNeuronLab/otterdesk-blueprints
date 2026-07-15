from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue
from runtime.runtime import (
    METHOD_IDS,
    METHOD_SCORER_FUNCTIONS,
    build_fact_table,
    company_worker_count,
    flattened_sources,
    normalized_research_ledger,
    run_scorers,
    scoring_worker_count,
)


def run_valuation_scoring_crew(ctx: dict[str, Any], *, llm_client: Any | None = None) -> dict[str, Any]:
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")

    def score_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        ledger = normalized_research_ledger(store.read_entity_object("research_ledgers", company))
        facts = build_fact_table(company, records, flattened_sources(ledger))
        results = run_scorers(
            [METHOD_SCORER_FUNCTIONS[method_id] for method_id in METHOD_IDS],
            facts,
            max_workers=scoring_worker_count(ctx["config"]),
        )
        by_method = {result["method_id"]: result for result in results}
        method_scores = {method_id: by_method[method_id] for method_id in METHOD_IDS}
        for method_id in METHOD_IDS:
            store.write_entity(f"method_scores_by_method/{method_id}", company, method_scores[method_id])
        store.write_entity("method_scores", company, method_scores)
        store.write_entity("company_fact_tables", company, facts)
        return {"company": company, "method_count": len(method_scores)}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=score_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: item.get("status") == "unchanged_skipped",
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    return {
        "method_count": len(METHOD_IDS),
        "processed_company_count": int(queue_result["processed_count"]),
        "skipped_company_count": int(queue_result["skipped_count"]),
    }
