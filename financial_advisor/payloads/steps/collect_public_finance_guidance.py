from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("analyze_portfolio_risk")),
    flow=agent("public_finance_researcher"),
    output=OutputSpec(fields={"public_finance_guidance": flow_output()}),
)
