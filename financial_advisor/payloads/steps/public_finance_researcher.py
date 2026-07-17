from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("financial_document_reader")), flow=agent("public_finance_researcher"), output=OutputSpec(fields={"public_research": flow_output()}))

