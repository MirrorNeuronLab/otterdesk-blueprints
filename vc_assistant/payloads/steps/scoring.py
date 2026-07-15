from __future__ import annotations

from mn_prototype_operation_router_agent import OperationBinding, OperationRouterSpec, create_agent

from agents.score_consistency_auditor import run_score_consistency_auditor_step
from agents.scoring_stage import run_scorer_step

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "berkus_method": OperationBinding(run_scorer_step, {"step_id": "berkus_scorer"}),
                "scorecard_bill_payne_method": OperationBinding(
                    run_scorer_step,
                    {"step_id": "scorecard_bill_payne_scorer"},
                ),
                "risk_factor_summation_method": OperationBinding(
                    run_scorer_step,
                    {"step_id": "risk_factor_summation_scorer"},
                ),
                "venture_capital_method": OperationBinding(
                    run_scorer_step,
                    {"step_id": "venture_capital_method_scorer"},
                ),
                "first_chicago_method": OperationBinding(run_scorer_step, {"step_id": "first_chicago_scorer"}),
                "comparables_market_multiple_method": OperationBinding(
                    run_scorer_step,
                    {"step_id": "comparables_market_multiple_scorer"},
                ),
                "cost_to_duplicate_method": OperationBinding(
                    run_scorer_step,
                    {"step_id": "cost_to_duplicate_scorer"},
                ),
                "audit": run_score_consistency_auditor_step,
            },
            selector="method",
            label="VC scoring method",
        )
    )
)
