from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("portfolio_context_loader")), flow=agent("portfolio_market_data_loader"), output=OutputSpec(fields={"market_data": flow_output()}))

