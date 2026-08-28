from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(
    input=InputSpec(fields=inputs("audit_architecture_advice")),
    flow=agent("architecture_artifact_publisher"),
    output=OutputSpec(fields={"architecture_advice": flow_output()}),
)
