from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("structure_generation")), flow=agent("candidate_generation"), output=OutputSpec(fields={"candidate_service": flow_output()}))

