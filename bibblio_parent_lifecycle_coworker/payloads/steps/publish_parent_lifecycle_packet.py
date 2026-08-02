from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("parent_feedback_file", previous_step="diagnose_parent_journey")),
    flow=agent("bibblio_parent_lifecycle_director"),
    output=OutputSpec(fields={"parent_lifecycle_packet": flow_output()}),
)

