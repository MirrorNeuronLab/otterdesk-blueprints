from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("target_discovery")), flow=agent("structure_generation"), output=OutputSpec(fields={"structures": flow_output()}))

