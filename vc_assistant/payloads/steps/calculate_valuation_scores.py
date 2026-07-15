from mn_sdk.step_graph import (
    InputSpec,
    OutputSpec,
    StepSpec,
    agent,
    flow_output,
    parallel,
)

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("reconcile_research_evidence", "reconciled_evidence")
    ),
    flow=parallel(
        agent("berkus_scorer"),
        agent("scorecard_bill_payne_scorer"),
        agent("risk_factor_summation_scorer"),
        agent("venture_capital_method_scorer"),
        agent("first_chicago_scorer"),
        agent("comparables_market_multiple_scorer"),
        agent("cost_to_duplicate_scorer"),
    ),
    output=OutputSpec(fields={"valuation_scores": flow_output()}),
)
