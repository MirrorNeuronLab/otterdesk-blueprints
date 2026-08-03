from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("customer_feedback_file", previous_step="diagnose_customer_journey")),
    flow=agent("customer_lifecycle_director"),
    output=OutputSpec(fields={"customer_lifecycle_packet": flow_output()}),
)
