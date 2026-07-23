from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("build_purchase_evidence")),
    flow=sequence(
        agent("purchase_market_researcher", as_="market"),
        agent("purchase_total_cost_analyst", as_="cost"),
        agent("purchase_risk_reviewer", as_="risk"),
        agent("purchase_recommendation_auditor", as_="audit"),
    ),
    output=OutputSpec(fields={"option_comparison": flow_output()}),
)
