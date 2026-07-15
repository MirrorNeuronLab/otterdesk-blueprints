from __future__ import annotations

from mn_prototype_operation_router_agent import OperationRouterSpec, create_agent

from agents.public_research_crew import run_public_research_crew
from agents.research_planner import run_research_planner
from agents.research_reconciler import run_research_reconciler

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "plan": run_research_planner,
                "collect": run_public_research_crew,
                "reconcile": run_research_reconciler,
            },
            label="VC research operation",
        )
    )
)
