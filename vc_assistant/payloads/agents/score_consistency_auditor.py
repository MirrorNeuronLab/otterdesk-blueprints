from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import slugify, write_workflow_state
from mn_prototype_entity_queue_agent import (
    EntityQueueSpec,
    create_agent as create_entity_queue,
)
from domain.common import METHOD_IDS
from domain.composition import build_company_analysis_from_method_scores
from domain.knowledge import public_knowledge_rag_state
from domain.execution_policy import company_worker_count, scoring_fund_profile
from domain.research_core import (
    agentic_research_config,
    normalized_research_ledger,
)
from domain.research_orchestration import reconcile_research

from ._shared import agent_output, create_agent_handler, durable_artifact, input_artifact


def run_score_consistency_auditor(
    ctx: dict[str, Any], *, llm_client: Any | None = None
) -> dict[str, Any]:
    input_artifact(ctx, "valuation_method_score_index")
    store = ctx["state_store"]
    company_records = store.read_object("company_records.json")
    company_work_queue = store.read_list("company_work_queue.json")
    services = ctx["services"]

    def audit_company(_context: dict[str, Any], item: dict[str, Any]) -> dict[str, Any]:
        company = str(item["company_name"])
        records = company_records.get(company, [])
        ledger = normalized_research_ledger(
            store.read_entity_object("research_ledgers", company)
        )
        methods = {
            method_id: score
            for method_id, score in store.read_entity_object(
                "method_scores", company
            ).items()
            if method_id in METHOD_IDS and isinstance(score, dict)
        }
        for method_id in METHOD_IDS:
            score = store.read_entity_object(
                f"method_scores_by_method/{method_id}", company
            )
            if score:
                methods[method_id] = score
        missing_methods = [
            method_id for method_id in METHOD_IDS if method_id not in methods
        ]
        if missing_methods:
            raise RuntimeError(
                f"Missing method scores for {company}: {', '.join(missing_methods)}"
            )
        analysis = build_company_analysis_from_method_scores(
            company,
            records,
            ledger,
            methods,
            fund_profile=scoring_fund_profile(ctx["config"]),
        )
        analysis["processing_status"] = "new_or_changed"
        analysis["cached_from_previous_run"] = False
        analysis["cache_policy"] = {
            **(item.get("cache_policy") or {}),
            "cache_source": "",
            "decision": "process_company_packet",
        }
        analysis["research_reconciliation"] = store.read_entity_object(
            "reconciliations", company
        ) or reconcile_research(records, ledger)
        analysis["research_plan"] = store.read_entity_object("research_plans", company)
        analysis["agent_tool_trace"] = [
            item
            for item in store.read_entity_list("agent_tool_traces", company)
            if isinstance(item, dict)
        ]
        analysis.setdefault("research_plan", {})["knowledge_rag"] = (
            public_knowledge_rag_state(services.get("knowledge_rag") or {})
        )
        analysis["research_plan"]["agentic_research"] = {
            "enabled": bool(agentic_research_config(ctx["config"]).get("enabled")),
            "agent_ids": agentic_research_config(ctx["config"]).get("agent_ids"),
            "allowed_tools": agentic_research_config(ctx["config"]).get(
                "allowed_tools"
            ),
            "max_iterations_per_agent": agentic_research_config(ctx["config"]).get(
                "max_iterations_per_agent"
            ),
            "max_tool_calls_per_agent": agentic_research_config(ctx["config"]).get(
                "max_tool_calls_per_agent"
            ),
            "stop_reasons": {
                trace.get("agent_id"): trace.get("stop_reason")
                for trace in analysis["agent_tool_trace"]
            },
        }
        store.write_entity("analyses", str(analysis["company_slug"]), analysis)
        store.write_entity("audit_findings", company, analysis["audit"])
        return {"company": company, "status": analysis["audit"]["status"]}

    queue_result = create_entity_queue(
        EntityQueueSpec(
            load_entities=lambda _context, **_options: company_work_queue,
            process_entity=audit_company,
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
    refs = [
        durable_artifact(
            "audited_company_analysis",
            f"workflow_state/analyses/{slugify(item['company_name'])}.json",
            company=item["company_name"],
        )
        for item in company_work_queue
        if item.get("status") != "unchanged_skipped"
    ]
    write_workflow_state(ctx["run_dir"], "audited_analysis_index.json", refs)
    index = durable_artifact(
        "audited_analysis_index", "workflow_state/audited_analysis_index.json"
    )
    return agent_output(
        {
            "processed_company_count": processed_count,
            "skipped_company_count": skipped_count,
            "audited_analysis_artifact": index,
        },
        index,
        *refs,
        metrics={"audited_company_count": processed_count},
    )


run = create_agent_handler(run_score_consistency_auditor)
