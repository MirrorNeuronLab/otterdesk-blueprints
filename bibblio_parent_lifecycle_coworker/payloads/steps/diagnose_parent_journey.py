from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("parent_feedback_file")),
    flow=agent("bibblio_parent_lifecycle_director"),
    output=OutputSpec(fields={"parent_journey_diagnosis": flow_output()}),
)

