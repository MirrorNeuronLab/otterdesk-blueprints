from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs()),
    flow=agent("purchase_intake_analyst"),
    output=OutputSpec(fields={"purchase_frame": flow_output()}),
)
