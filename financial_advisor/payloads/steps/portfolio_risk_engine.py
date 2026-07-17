from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("portfolio_market_data_loader")), flow=agent("portfolio_risk_engine"), output=OutputSpec(fields={"portfolio_risk": flow_output()}))

