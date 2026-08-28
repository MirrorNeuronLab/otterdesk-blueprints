from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(input=InputSpec(fields=inputs()), flow=agent("source_intake_analyst"), output=OutputSpec(fields={"source": flow_output()}))
