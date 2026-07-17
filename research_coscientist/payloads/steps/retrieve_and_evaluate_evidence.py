from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("frame_research_goal")), flow=agent("retrieve_and_evaluate_evidence"), output=OutputSpec(fields={"retrieved_evidence": flow_output()}))

