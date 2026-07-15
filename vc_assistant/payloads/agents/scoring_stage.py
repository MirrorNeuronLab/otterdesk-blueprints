from __future__ import annotations

from typing import Any

from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue
from mn_sdk.blueprint_support import complete_runtime_step, step_result
from runtime.runtime import (
    METHOD_SCORER_FUNCTIONS,
    SCORER_METHOD_BY_STAGE,
    build_fact_table,
    company_worker_count,
    flattened_sources,
    normalized_research_ledger,
)

def run_scorer_step(ctx: dict[str, Any], step_id: str, *, llm_client: Any | None = None) -> dict[str, Any]:
    method_id = SCORER_METHOD_BY_STAGE[step_id]
    scorer = METHOD_SCORER_FUNCTIONS[method_id]
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    def process_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        ledger = normalized_research_ledger(store.read_entity_object("research_ledgers", company))
        facts = build_fact_table(company, records, flattened_sources(ledger))
        store.write_entity(f"method_scores_by_method/{method_id}", company, scorer(facts))
        store.write_entity("company_fact_tables", company, facts)
        return {"company": company, "method_id": method_id}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=process_company,
            entity_id=lambda item: str(item["company_name"]),
            should_skip=lambda _context, item, **_options: item.get("status") == "unchanged_skipped",
            max_workers=lambda _context, **_options: company_worker_count(
                ctx["config"], len(company_work_queue)
            ),
        )
    )(ctx)
    processed_count = int(queue_result["processed_count"])
    skipped_count = int(queue_result["skipped_count"])
    complete_runtime_step(ctx, step_id, {"method_id": method_id, "company_count": processed_count, "skipped_company_count": skipped_count})
    return step_result(ctx, step_id, method_id=method_id, processed_company_count=processed_count, skipped_company_count=skipped_count)
