from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("cash_flow_normalizer")), flow=agent("cash_flow_llm_analyst"), output=OutputSpec(fields={"cash_flow_review": flow_output()}))

