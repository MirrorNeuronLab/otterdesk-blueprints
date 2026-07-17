from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs()), flow=agent("collect_purchase_context"), output=OutputSpec(fields={"purchase_context": flow_output()}))

