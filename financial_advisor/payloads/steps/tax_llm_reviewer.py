from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output
from ._shared import inputs
STEP = StepSpec(input=InputSpec(fields=inputs("tax_workpaper_preparer")), flow=agent("tax_llm_reviewer"), output=OutputSpec(fields={"tax_review": flow_output()}))

