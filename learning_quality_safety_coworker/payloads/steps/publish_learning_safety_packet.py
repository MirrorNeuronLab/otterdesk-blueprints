from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("content_backlog_file", previous_step="review_learning_backlog")),
    flow=agent("learning_quality_safety_director"),
    output=OutputSpec(fields={"learning_safety_packet": flow_output()}),
)

