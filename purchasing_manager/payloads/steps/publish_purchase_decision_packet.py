from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(
        fields=inputs("audit_purchase_recommendation", "audited_recommendation")
    ),
    flow=agent("purchase_report_writer"),
    output=OutputSpec(fields={"purchase_decision_packet": flow_output()}),
)
