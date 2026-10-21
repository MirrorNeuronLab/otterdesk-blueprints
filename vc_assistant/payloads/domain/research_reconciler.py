"""Verify the declared research join and reconcile domain evidence natively."""

from mn_blueprint_blocks.context import Capability
from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify
from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue

from .common import RESEARCH_AGENT_IDS
from .execution_policy import company_worker_count
from .intake_state import checkpoint_path, merge_actor_reviews, publish_snapshot, read_snapshot, snapshot_reference
from .research_core import normalized_research_ledger
from .research_orchestration import append_financial_tool_research, reconcile_research
from .research_services import research_resources
from .research_policy import build_fact_table
from mn_public_research_orchestrator_skill import flatten_research_ledger


def join_research(block, references):
    if set(references) != set(RESEARCH_AGENT_IDS):
        raise ValueError("VC reconciliation requires exactly its declared research specialists")
    branches = {role: read_snapshot(block, {"previous": {"state": reference}}, role)
        for role, reference in references.items()}
    first = next(iter(branches.values()))["research_branch"]["base"]
    state = block.read_checkpoint(first, expected_path=checkpoint_path("research_planner"))
    companies = {item["company_name"] for item in state["queue"] if item.get("status") != "unchanged_skipped"}
    for role in RESEARCH_AGENT_IDS:
        snapshot = branches[role]
        branch = snapshot["research_branch"]
        if (branch.get("agent_id") != role or branch.get("base") != first
            or set(branch.get("sources", {})) != companies or set(branch.get("traces", {})) != companies):
            raise ValueError("VC research branch authority or company coverage changed")
        for company in companies:
            ledger = normalized_research_ledger(state["cached"]["research_ledgers"].get(company) or {})
            ledger[role] = ledger.get(role, []) + branch["sources"][company]
            state["cached"]["research_ledgers"][company] = normalized_research_ledger(ledger)
            state["cached"]["agent_tool_traces"].setdefault(company, []).extend(branch["traces"][company])
    merge_actor_reviews(state, {role: branches[role] for role in RESEARCH_AGENT_IDS})
    state["research_branches"] = references
    return state


def reconcile_snapshot(block, state):
    resources = research_resources(block, state, "research_reconciler", need_model=False,
        need_knowledge=False, budget_scope="reconciliation")
    state["fact_tables"] = {}

    def reconcile_company(_block, item):
        block.check()
        company = item["company_name"]
        records = state["records"].get(company, [])
        ledger = normalized_research_ledger(state["cached"]["research_ledgers"].get(company) or {})
        append_financial_tool_research(company, records, ledger,
            action_budget=resources.budget, run_dir=block.store.run_dir)
        state["cached"]["research_ledgers"][company] = normalized_research_ledger(ledger)
        state["cached"]["reconciliations"][company] = reconcile_research(records, ledger)
        state["fact_tables"][company] = build_fact_table(company, records, flatten_research_ledger(ledger))
        return {"company": company, "reconciled": True}

    queue = create_entity_queue(EntityQueueSpec(load_entities=lambda _block: state["queue"],
        process_entity=reconcile_company, entity_id=lambda item: item["company_name"],
        should_skip=lambda _block, item: item.get("status") == "unchanged_skipped",
        max_workers=company_worker_count(block.config, len(state["queue"]))))(block)
    state["action_ledger"] = resources.budget.summary(include_actions=True)
    return state, queue


@activity_operation('Reconciling company research', completed='Reconciling company research: completed')
def research_reconciler(block, inputs):
    packets = inputs.get("previous")
    if not isinstance(packets, dict) or set(packets) != set(RESEARCH_AGENT_IDS):
        raise ValueError("VC reconciliation requires its explicit research join")
    references = {role: snapshot_reference({"previous": packet.get("result")})
        for role, packet in packets.items()}
    join_research(block, references)

    def reconcile(request):
        state = join_research(block, request.data["branches"])
        state, queue = reconcile_snapshot(block, state)
        return {"state": state, "queue": queue}

    block.register_capability("vc_reconcile_research", Capability(reconcile, block.revision))
    result = block.invoke("vc_reconcile_research", {"branches": references}, key="reconcile")
    state, queue = result["state"], result["queue"]
    views = {f"{collection}/{slugify(company)}.json": value
        for collection, values in state["cached"].items() for company, value in values.items()}
    return publish_snapshot(block, state, "research_reconciler",
        {"processed_company_count": queue["processed_count"], "skipped_company_count": queue["skipped_count"]}, views)
