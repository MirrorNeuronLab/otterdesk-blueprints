from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("content_backlog_file")),
    flow=agent("learning_quality_safety_director"),
    output=OutputSpec(fields={"learning_backlog_review": flow_output()}),
)

