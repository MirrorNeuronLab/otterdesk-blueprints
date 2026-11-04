from mn_sdk.blueprint.steps import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(fields=step_inputs()),
    flow=agent("startup_folder_watcher"),
    output=OutputSpec(fields={"packet_changes": flow_output()}),
)
