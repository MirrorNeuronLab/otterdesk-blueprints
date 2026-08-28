from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(input=InputSpec(fields=inputs("assess_architecture_improvements")), flow=agent("improvement_prompt_author"), output=OutputSpec(fields={"prompt_pack": flow_output()}))
