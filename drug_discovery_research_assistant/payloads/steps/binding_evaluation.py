from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("candidate_generation")), flow=agent("binding_evidence_reviewer"), output=OutputSpec(fields={"evaluations": flow_output()}))
