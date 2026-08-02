from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("learning_briefs_file")),
    flow=agent("bibblio_content_studio_director"),
    output=OutputSpec(fields={"draft_content_batch": flow_output()}),
)

