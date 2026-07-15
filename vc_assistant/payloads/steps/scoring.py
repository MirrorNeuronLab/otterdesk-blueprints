from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.score_consistency_auditor import run_score_consistency_auditor
from agents.valuation_scoring_crew import run_valuation_scoring_crew

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "calculate": run_valuation_scoring_crew,
                "audit": run_score_consistency_auditor,
            },
            label="VC scoring operation",
        )
    )
)
