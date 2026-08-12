from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(
        fields=inputs(previous_step="deliver_approved_lifecycle_email")
    ),
    flow=agent("development_reply_monitor"),
    output=OutputSpec(fields={"development_reply_monitoring": flow_output()}),
)
