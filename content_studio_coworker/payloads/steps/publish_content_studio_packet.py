from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("learning_briefs_file", previous_step="plan_content_batch")),
    flow=agent("bibblio_content_studio_director"),
    output=OutputSpec(fields={"content_studio_packet": flow_output()}),
)

