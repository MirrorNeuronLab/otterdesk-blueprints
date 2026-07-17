from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs()), flow=agent("target_discovery"), output=OutputSpec(fields={"targets": flow_output()}))

