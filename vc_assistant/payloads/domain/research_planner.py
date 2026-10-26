"""Native VC research planning from immutable intake evidence."""

from mn_blueprint_blocks.context import Capability
from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify
from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue

from .execution_policy import company_worker_count
from .intake_state import checkpoint_path, publish_snapshot, read_snapshot, snapshot_reference
from .knowledge import require_ready_rag, retrieve_knowledge_rag_context
from .research_agentic import build_research_agent_rag_query, run_agentic_research_agent
from .research_core import _research_agent_enabled, agentic_research_config, normalized_research_ledger
from .research_policy import build_adaptive_research_plan
from .research_services import reconcile_research_effect, research_resources


def plan_snapshot(block, state):
    internet = block.config.get("internet_research") or {}
    agentic = agentic_research_config(block.config)
    needs_model = bool(agentic.get("enabled")) and _research_agent_enabled(agentic, "research_planner")
    resources = research_resources(block, state, "research_planner", need_model=needs_model,
        need_knowledge=needs_model, budget_scope="planning")
    cached = state["cached"]
    plans = {item["company_name"]: build_adaptive_research_plan(
        item["company_name"], state["records"].get(item["company_name"], []), internet)
        for item in state["queue"]}
    contexts = {}
    # Finish query-specific embedding retrieval before starting actor calls.
    if needs_model:
        for item in state["queue"]:
            block.check()
            if item.get("status") == "unchanged_skipped":
                continue
            company = item["company_name"]
            selected = retrieve_knowledge_rag_context(knowledge_rag=resources.rag,
                query=build_research_agent_rag_query(agent_id="research_planner", plan=plans[company]),
                stage="research_planner", company=company, run_dir=block.store.run_dir)
            require_ready_rag(resources.rag, stage="research_planner", company=company,
                context=selected, min_citations=1, run_dir=block.store.run_dir)
            contexts[company] = selected

    def plan_company(_block, item):
        block.check()
        company = item["company_name"]
        plan = plans[company]
        if item.get("status") == "unchanged_skipped":
            if company in cached["analyses"]:
                cached["analyses"][company]["research_plan"] = plan
        elif needs_model:
            trace = list(cached["agent_tool_traces"].get(company) or [])
            _, sources = run_agentic_research_agent(company=company, agent_id="research_planner",
                plan=plan, internet=internet, run_dir=block.store.run_dir,
                action_budget=resources.budget, llm=resources.model, agentic=agentic,
                trace=trace, knowledge_rag=resources.rag, rag_context=contexts[company])
            ledger = normalized_research_ledger(cached["research_ledgers"].get(company) or {})
            ledger["company_identity_researcher"] = sources + ledger.get("company_identity_researcher", [])
            cached["research_ledgers"][company] = normalized_research_ledger(ledger)
            cached["agent_tool_traces"][company] = trace
        return {"company": company, "planned": True}

    create_entity_queue(EntityQueueSpec(load_entities=lambda _block: state["queue"],
        process_entity=plan_company, entity_id=lambda item: item["company_name"],
        max_workers=company_worker_count(block.config, len(state["queue"]))))(block)
    cached["research_plans"] = plans
    state["action_ledger"] = resources.budget.summary(include_actions=True)
    return state


@activity_operation('Planning company research', completed='Planning company research: completed')
def research_planner(block, inputs):
    read_snapshot(block, inputs, "claim_normalizer")

    def plan(request):
        state = block.read_checkpoint(request.data["state"], expected_path=checkpoint_path("claim_normalizer"))
        return plan_snapshot(block, state)

    # Planning can include billed models and browser tools. Freeze its complete
    # response before optional review; an interrupted outcome fences redispatch.
    block.register_capability("vc_research_plan", Capability(plan, block.revision,
        reconcile=lambda _request: reconcile_research_effect(block, budget_scope="planning")))
    state = block.invoke("vc_research_plan", {"state": snapshot_reference(inputs)}, key="plan")
    views = {f"{collection}/{slugify(company)}.json": value
        for collection, values in state["cached"].items() for company, value in values.items()}
    views["action_ledger.json"] = state["action_ledger"]
    return publish_snapshot(block, state, "research_planner",
        {"company_count": len(state["queue"])}, views)
