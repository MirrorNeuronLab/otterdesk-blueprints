from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("portfolio_risk_engine")), flow=agent("portfolio_llm_reviewer"), output=OutputSpec(fields={"portfolio_review": flow_output()}))

