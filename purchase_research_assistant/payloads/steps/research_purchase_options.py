from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("retrieve_purchase_knowledge")), flow=agent("research_purchase_options"), output=OutputSpec(fields={"purchase_options": flow_output()}))

