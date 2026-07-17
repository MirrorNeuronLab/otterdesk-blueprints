from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs()), flow=agent("frame_research_goal"), output=OutputSpec(fields={"research_context": flow_output()}))

