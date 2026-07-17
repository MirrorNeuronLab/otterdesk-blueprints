from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("retrieve_and_evaluate_evidence")), flow=agent("autonomous_research"), output=OutputSpec(fields={"autonomous_session": flow_output()}))

