from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("bank_statement_extractor")), flow=agent("cash_flow_normalizer"), output=OutputSpec(fields={"cash_flow": flow_output()}))

