from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

STEP = StepSpec(
    input=InputSpec(fields={"previous": upstream("capture_repository")}),
    flow=agent("architecture_structure_analyst"),
    output=OutputSpec(fields={"result": flow_output()}),
)
