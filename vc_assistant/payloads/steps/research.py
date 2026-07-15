from __future__ import annotations

from mn_prototype_operation_router_agent import OperationBinding, OperationRouterSpec, create_agent

from agents.research_planner import run_research_planner_step
from agents.research_reconciler import run_research_reconciler_step
from agents.research_stage import run_research_stage_step

from ._shared import compose


run = compose(
    create_agent(
        OperationRouterSpec(
            operations={
                "plan": run_research_planner_step,
                "company_identity": OperationBinding(
                    run_research_stage_step,
                    {"step_id": "company_identity_researcher"},
                ),
                "funding": OperationBinding(
                    run_research_stage_step,
                    {"step_id": "funding_researcher"},
                ),
                "market_comparables": OperationBinding(
                    run_research_stage_step,
                    {"step_id": "market_comp_researcher"},
                ),
                "traction": OperationBinding(
                    run_research_stage_step,
                    {"step_id": "traction_verifier"},
                ),
                "rendered_pages": OperationBinding(
                    run_research_stage_step,
                    {"step_id": "rendered_page_researcher"},
                ),
                "reconcile": run_research_reconciler_step,
            },
            label="VC research operation",
        )
    )
)
