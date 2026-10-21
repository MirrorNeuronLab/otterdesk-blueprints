"""Native method specialists over one reconciled evidence checkpoint."""

from mn_sdk.agent_events import activity_operation
from mn_sdk.blueprint_support import slugify
from mn_sdk.step_runtime import artifact_reference
from mn_prototype_entity_queue_agent import EntityQueueSpec, create_agent as create_entity_queue

from .common import SCORER_AGENT_BY_METHOD
from .execution_policy import company_worker_count
from .intake_state import publish_snapshot, read_snapshot, snapshot_reference
from .valuation import METHOD_SCORER_FUNCTIONS


def score_snapshot(block, state, role, base):
    method = next(method for method, agent in SCORER_AGENT_BY_METHOD.items() if agent == role)
    scorer = METHOD_SCORER_FUNCTIONS[method]
    branch = {"agent_id": role, "method": method, "base": base, "scores": {}, "facts": {}}

    def score_company(_block, item):
        block.check()
        company = item["company_name"]
        facts = state["fact_tables"][company]
        branch["facts"][company], branch["scores"][company] = facts, scorer(facts)
        block.check()
        return {"company": company, "method": method, "status": branch["scores"][company]["status"]}

    create_entity_queue(EntityQueueSpec(load_entities=lambda _block: state["queue"],
        process_entity=score_company, entity_id=lambda item: item["company_name"],
        should_skip=lambda _block, item: item.get("status") == "unchanged_skipped",
        max_workers=company_worker_count(block.config, len(state["queue"]))))(block)
    state["score_branch"] = branch
    return state


def score_evidence(block, inputs, role):
    state = read_snapshot(block, inputs, "research_reconciler")
    path = block.root + "/prepared-score.json"
    reference = block.freeze_checkpoint(path,
        lambda: score_snapshot(block, state, role, snapshot_reference(inputs)))
    state = block.read_checkpoint(reference, expected_path=path)
    branch = state["score_branch"]
    method = branch["method"]
    index_path = f"method_score_indexes/{method}.json"
    refs = [artifact_reference("valuation_method_score",
        f"workflow_state/method_scores_by_method/{method}/{slugify(company)}.json",
        company=company, method=method) for company in branch["scores"]]
    index = artifact_reference("valuation_method_score_index", "workflow_state/" + index_path, method=method)
    views = {f"{collection}/{method}/{slugify(company)}.json": value
        for collection, values in (("method_scores_by_method", branch["scores"]),
                                   ("company_fact_tables_by_method", branch["facts"]))
        for company, value in values.items()}
    return publish_snapshot(block, state, role,
        {"method": method, "processed_company_count": len(branch["scores"]),
         "skipped_company_count": len(state["queue"]) - len(branch["scores"]),
         "method_scores_artifact": index, "artifacts": [index, *refs]},
        {**views, index_path: refs})


@activity_operation('Calculating Berkus scores', completed='Calculating Berkus scores: completed')
def berkus_scorer(block, inputs):
    return score_evidence(block, inputs, "berkus_scorer")


@activity_operation('Calculating Scorecard scores', completed='Calculating Scorecard scores: completed')
def scorecard_bill_payne_scorer(block, inputs):
    return score_evidence(block, inputs, "scorecard_bill_payne_scorer")


@activity_operation('Calculating Risk Factor Summation scores', completed='Calculating Risk Factor Summation scores: completed')
def risk_factor_summation_scorer(block, inputs):
    return score_evidence(block, inputs, "risk_factor_summation_scorer")


@activity_operation('Calculating Venture Capital Method scores', completed='Calculating Venture Capital Method scores: completed')
def venture_capital_method_scorer(block, inputs):
    return score_evidence(block, inputs, "venture_capital_method_scorer")


@activity_operation('Calculating First Chicago scores', completed='Calculating First Chicago scores: completed')
def first_chicago_scorer(block, inputs):
    return score_evidence(block, inputs, "first_chicago_scorer")


@activity_operation('Calculating Comparables scores', completed='Calculating Comparables scores: completed')
def comparables_market_multiple_scorer(block, inputs):
    return score_evidence(block, inputs, "comparables_market_multiple_scorer")


@activity_operation('Calculating Cost-to-Duplicate scores', completed='Calculating Cost-to-Duplicate scores: completed')
def cost_to_duplicate_scorer(block, inputs):
    return score_evidence(block, inputs, "cost_to_duplicate_scorer")
