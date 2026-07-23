from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("compare_purchase_options")),
    flow=agent("purchase_report_writer"),
    output=OutputSpec(fields={"purchase_decision_packet": flow_output()}),
)
