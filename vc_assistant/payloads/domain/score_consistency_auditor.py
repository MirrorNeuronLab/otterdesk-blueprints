"""Verify the seven declared score branches and audit their domain results."""

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify
from mn_sdk.step_runtime import artifact_reference
from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue

from .common import SCORER_AGENT_BY_METHOD
from .composition import build_company_analysis_from_method_scores
from .execution_policy import company_worker_count, scoring_fund_profile
from .intake_state import checkpoint_path, merge_actor_reviews, publish_snapshot, read_snapshot, snapshot_reference
from .knowledge import public_knowledge_rag_state
from .research_core import actor_review_config, agentic_research_config
from .research_services import research_resources


def join_scores(block, packets):
    roles = set(SCORER_AGENT_BY_METHOD.values())
    if not isinstance(packets, dict) or set(packets) != roles:
        raise ValueError("VC audit requires exactly its declared scoring specialists")
    references = {role: snapshot_reference({"previous": packet.get("result")})
        for role, packet in packets.items()}
    branches = {role: read_snapshot(block, {"previous": {"state": reference}}, role)
        for role, reference in references.items()}
    base = next(iter(branches.values()))["score_branch"]["base"]
    state = block.read_checkpoint(base, expected_path=checkpoint_path("research_reconciler"))
    companies = {item["company_name"] for item in state["queue"] if item.get("status") != "unchanged_skipped"}
    methods = {company: {} for company in companies}
    for method, role in SCORER_AGENT_BY_METHOD.items():
        branch = branches[role]["score_branch"]
        if (branch.get("agent_id") != role or branch.get("method") != method or branch.get("base") != base
            or set(branch.get("scores", {})) != companies or set(branch.get("facts", {})) != companies):
            raise ValueError("VC score branch authority or company coverage changed")
        for company in companies:
            if branch["scores"][company].get("method_id") != method:
                raise ValueError("VC score result belongs to another method")
            if state["fact_tables"][company] != branch["facts"][company]:
                raise ValueError("VC score branches used different company facts")
            methods[company][method] = branch["scores"][company]
    merge_actor_reviews(state, {role: branches[role] for role in SCORER_AGENT_BY_METHOD.values()})
    state["scoring_branches"] = references
    return state, methods


def audit_snapshot(block, packets):
    state, methods = join_scores(block, packets)
    role = "score_consistency_auditor"
    resources = research_resources(block, state, role, need_model=False,
        need_knowledge=role in actor_review_config(block.config)["llm_actor_ids"], budget_scope="scoring-audit")
    cached, agentic = state["cached"], agentic_research_config(block.config)

    def audit_company(_block, item):
        block.check()
        company = item["company_name"]
        analysis = build_company_analysis_from_method_scores(company,
            state["records"].get(company, []), cached["research_ledgers"].get(company) or {},
            methods[company], fund_profile=scoring_fund_profile(block.config),
            fact_table=state["fact_tables"][company], source_scope={"job_id": block.job_id, "run_id": block.run_id})
        analysis.update(processing_status="new_or_changed", cached_from_previous_run=False,
            cache_policy={**(item.get("cache_policy") or {}), "cache_source": "", "decision": "process_company_packet"},
            research_reconciliation=cached["reconciliations"][company],
            research_plan=cached["research_plans"][company],
            agent_tool_trace=cached["agent_tool_traces"].get(company, []))
        analysis["research_plan"].update(knowledge_rag=public_knowledge_rag_state(resources.rag),
            agentic_research={**{key: agentic.get(key) for key in
                ("enabled", "agent_ids", "allowed_tools", "max_iterations_per_agent", "max_tool_calls_per_agent")},
                "stop_reasons": {trace.get("agent_id"): trace.get("stop_reason") for trace in analysis["agent_tool_trace"]}})
        cached["analyses"][company], cached["method_scores"][company] = analysis, methods[company]
        state["evidence"][company] = {key: analysis[key] for key in ("source_records", "evidence_items", "claim_records")}
        block.check()
        return {"company": company, "status": analysis["audit"]["status"]}

    create_entity_queue(EntityQueueSpec(load_entities=lambda _block: state["queue"],
        process_entity=audit_company, entity_id=lambda item: item["company_name"],
        should_skip=lambda _block, item: item.get("status") == "unchanged_skipped",
        max_workers=company_worker_count(block.config, len(state["queue"]))))(block)
    state["action_ledger"] = resources.budget.summary(include_actions=True)
    return state


@activity_operation('Auditing valuation consistency', completed='Auditing valuation consistency: completed')
def score_consistency_auditor(block, inputs):
    packets = inputs.get("previous")
    join_scores(block, packets)
    path = block.root + "/prepared-audit.json"
    reference = block.freeze_checkpoint(path, lambda: audit_snapshot(block, packets))
    state = block.read_checkpoint(reference, expected_path=path)
    active = [item["company_name"] for item in state["queue"] if item.get("status") != "unchanged_skipped"]
    refs = [artifact_reference("audited_company_analysis", f"workflow_state/analyses/{slugify(company)}.json",
        company=company) for company in active]
    index = artifact_reference("audited_analysis_index", "workflow_state/audited_analysis_index.json")
    views = {f"analyses/{slugify(company)}.json": analysis for company, analysis in state["cached"]["analyses"].items()}
    views.update({f"audit_findings/{slugify(company)}.json": state["cached"]["analyses"][company]["audit"] for company in active})
    return publish_snapshot(block, state, "score_consistency_auditor",
        {"processed_company_count": len(active), "skipped_company_count": len(state["queue"]) - len(active),
         "audited_analysis_artifact": index, "artifacts": [index, *refs]},
        {**views, "audited_analysis_index.json": refs})
