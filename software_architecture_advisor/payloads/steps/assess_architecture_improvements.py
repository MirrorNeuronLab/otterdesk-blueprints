from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(input=InputSpec(fields=inputs("map_architecture_evidence")), flow=agent("architecture_reviewer"), output=OutputSpec(fields={"architecture_assessment": flow_output()}))
