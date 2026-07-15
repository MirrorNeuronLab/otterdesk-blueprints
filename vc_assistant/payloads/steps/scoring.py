from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from agents.berkus_scorer import run_berkus_scorer_step
from agents.comparables_market_multiple_scorer import run_comparables_market_multiple_scorer_step
from agents.cost_to_duplicate_scorer import run_cost_to_duplicate_scorer_step
from agents.first_chicago_scorer import run_first_chicago_scorer_step
from agents.risk_factor_summation_scorer import run_risk_factor_summation_scorer_step
from agents.score_consistency_auditor import run_score_consistency_auditor_step
from agents.scorecard_bill_payne_scorer import run_scorecard_bill_payne_scorer_step
from agents.venture_capital_method_scorer import run_venture_capital_method_scorer_step

from ._shared import execute


METHODS = {
    "berkus_method": run_berkus_scorer_step,
    "scorecard_bill_payne_method": run_scorecard_bill_payne_scorer_step,
    "risk_factor_summation_method": run_risk_factor_summation_scorer_step,
    "venture_capital_method": run_venture_capital_method_scorer_step,
    "first_chicago_method": run_first_chicago_scorer_step,
    "comparables_market_multiple_method": run_comparables_market_multiple_scorer_step,
    "cost_to_duplicate_method": run_cost_to_duplicate_scorer_step,
    "audit": run_score_consistency_auditor_step,
}


def run(context: StepContext, method: str, **options: Any) -> dict[str, Any]:
    try:
        handler = METHODS[method]
    except KeyError as exc:
        raise ValueError(f"unknown VC scoring method: {method}") from exc
    return execute(context, handler, **options)
