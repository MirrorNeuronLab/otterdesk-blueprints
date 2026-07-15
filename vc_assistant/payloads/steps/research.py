from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from agents.company_identity_researcher import run_company_identity_researcher_step
from agents.funding_researcher import run_funding_researcher_step
from agents.market_comp_researcher import run_market_comp_researcher_step
from agents.rendered_page_researcher import run_rendered_page_researcher_step
from agents.research_planner import run_research_planner_step
from agents.research_reconciler import run_research_reconciler_step
from agents.traction_verifier import run_traction_verifier_step

from ._shared import execute


OPERATIONS = {
    "plan": run_research_planner_step,
    "company_identity": run_company_identity_researcher_step,
    "funding": run_funding_researcher_step,
    "market_comparables": run_market_comp_researcher_step,
    "traction": run_traction_verifier_step,
    "rendered_pages": run_rendered_page_researcher_step,
    "reconcile": run_research_reconciler_step,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        handler = OPERATIONS[operation]
    except KeyError as exc:
        raise ValueError(f"unknown VC research operation: {operation}") from exc
    return execute(context, handler, **options)
