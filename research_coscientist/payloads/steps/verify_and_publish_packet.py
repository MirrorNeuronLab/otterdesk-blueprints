from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("autonomous_research")), flow=agent("verify_and_publish_packet"), output=OutputSpec(fields={"research_packet": flow_output()}))

