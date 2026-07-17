from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import slugify, write_workflow_state
from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from mn_public_research_orchestrator_skill import flatten_research_ledger
from domain.execution_policy import company_worker_count
from domain.research_core import normalized_research_ledger
from domain.research_policy import build_fact_table
from domain.valuation import METHOD_SCORER_FUNCTIONS

from ._shared import agent_output, create_agent_handler, durable_artifact, input_artifact


def run_valuation_scorer(
    ctx: dict[str, Any],
    *,
    method: str,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    input_artifact(ctx, "reconciled_research_index")
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
        facts = build_fact_table(company, records, flatten_research_ledger(ledger))
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
    refs = [
        durable_artifact(
            "valuation_method_score",
            f"workflow_state/method_scores_by_method/{method}/{slugify(item['company_name'])}.json",
            company=item["company_name"],
            method=method,
        )
        for item in company_work_queue
        if item.get("status") != "unchanged_skipped"
    ]
    index_name = f"method_score_indexes/{method}.json"
    write_workflow_state(ctx["run_dir"], index_name, refs)
    index = durable_artifact(
        "valuation_method_score_index", f"workflow_state/{index_name}", method=method
    )
    return agent_output(
        {
            "method": method,
            "processed_company_count": int(queue_result["processed_count"]),
            "skipped_company_count": int(queue_result["skipped_count"]),
            "method_scores_artifact": index,
        },
        index,
        *refs,
        metrics={"scored_company_count": int(queue_result["processed_count"])},
    )


def create_valuation_scorer():
    """Create a scorer whose immutable method binding comes from the manifest."""

    def run_method(
        ctx: dict[str, Any], *, method: str, llm_client: Any | None = None
    ) -> dict[str, Any]:
        return run_valuation_scorer(ctx, method=method, llm_client=llm_client)

    return create_agent_handler(run_method)


__all__ = ["create_valuation_scorer", "run_valuation_scorer"]
