"""Native public-research specialists over one verified planning snapshot."""

from mn_blueprint_blocks.context import Capability
from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify
from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue

from .execution_policy import company_worker_count
from .intake_state import checkpoint_path, read_snapshot, publish_snapshot, snapshot_reference
from .knowledge import require_ready_rag, retrieve_knowledge_rag_context
from .research_agentic import build_research_agent_rag_query, run_agentic_research_agent
from .research_core import agentic_research_config, _research_agent_enabled
from .research_orchestration import _run_research_agent, _with_agentic_gap_fill
from .research_services import reconcile_research_effect, research_resources


def collect_snapshot(block, state, role, base):
    internet = block.config.get("internet_research") or {}
    agentic = agentic_research_config(block.config)
    use_model = internet.get("enabled") is not False and _research_agent_enabled(agentic, role)
    resources = research_resources(block, state, role, need_model=use_model,
        need_knowledge=use_model, budget_scope="public-research")
    plans = state["cached"]["research_plans"]
    contexts = {}
    if use_model:
        for item in state["queue"]:
            block.check()
            if item.get("status") == "unchanged_skipped":
                continue
            company = item["company_name"]
            selected = retrieve_knowledge_rag_context(knowledge_rag=resources.rag,
                query=build_research_agent_rag_query(agent_id=role, plan=plans[company]),
                stage=role, company=company, run_dir=block.store.run_dir)
            require_ready_rag(resources.rag, stage=role, company=company, context=selected,
                min_citations=1, run_dir=block.store.run_dir)
            contexts[company] = selected
    branch = {"agent_id": role, "base": base, "sources": {}, "traces": {}}

    def research_company(_block, item):
        block.check()
        company = item["company_name"]
        plan, trace = plans[company], []
        query = (plan.get("agent_queries") or {}).get(role, [])
        if internet.get("enabled") is False:
            sources = []
        elif use_model:
            _, sources = run_agentic_research_agent(company=company, agent_id=role, plan=plan,
                internet=internet, run_dir=block.store.run_dir, action_budget=resources.budget,
                llm=resources.model, agentic=agentic, trace=trace, knowledge_rag=resources.rag,
                rag_context=contexts[company])
            _, sources = _with_agentic_gap_fill(company=company, agent_id=role,
                sources=sources, query=query, plan=plan, internet=internet,
                run_dir=block.store.run_dir, action_budget=resources.budget)
        else:
            _, sources = _run_research_agent(company, role, query, plan, internet,
                block.store.run_dir, resources.budget)
        branch["sources"][company], branch["traces"][company] = sources, trace
        block.check()
        return {"company": company, "source_count": len(sources)}

    create_entity_queue(EntityQueueSpec(load_entities=lambda _block: state["queue"],
        process_entity=research_company, entity_id=lambda item: item["company_name"],
        should_skip=lambda _block, item: item.get("status") == "unchanged_skipped",
        max_workers=company_worker_count(block.config, len(state["queue"]))))(block)
    state["research_branch"] = branch
    state["action_ledger"] = resources.budget.summary(include_actions=True)
    return state


def collect_evidence(block, inputs, role):
    read_snapshot(block, inputs, "research_planner")
    base = snapshot_reference(inputs)

    def collect(request):
        state = block.read_checkpoint(request.data["state"], expected_path=checkpoint_path("research_planner"))
        return collect_snapshot(block, state, role, request.data["state"])

    block.register_capability("vc_public_research", Capability(collect, block.revision,
        reconcile=lambda _request: reconcile_research_effect(block, budget_scope="public-research")))
    state = block.invoke("vc_public_research", {"state": base}, key="collect")
    branch = state["research_branch"]
    views = {**{f"research_ledgers_by_agent/{role}/{slugify(company)}.json": sources
        for company, sources in branch["sources"].items()},
        **{f"agent_tool_traces_by_agent/{role}/{slugify(company)}.json": trace
        for company, trace in branch["traces"].items()}}
    return publish_snapshot(block, state, role,
        {"agent_id": role, "processed_company_count": len(branch["sources"]),
         "skipped_company_count": len(state["queue"]) - len(branch["sources"])}, views)


@activity_operation('Researching company identity', completed='Researching company identity: completed')
def company_identity_researcher(block, inputs):
    return collect_evidence(block, inputs, "company_identity_researcher")


@activity_operation('Researching company funding', completed='Researching company funding: completed')
def funding_researcher(block, inputs):
    return collect_evidence(block, inputs, "funding_researcher")


@activity_operation('Researching markets and comparables', completed='Researching markets and comparables: completed')
def market_comp_researcher(block, inputs):
    return collect_evidence(block, inputs, "market_comp_researcher")


@activity_operation('Verifying company traction', completed='Verifying company traction: completed')
def traction_verifier(block, inputs):
    return collect_evidence(block, inputs, "traction_verifier")


@activity_operation('Researching rendered public pages', completed='Researching rendered public pages: completed')
def rendered_page_researcher(block, inputs):
    return collect_evidence(block, inputs, "rendered_page_researcher")
