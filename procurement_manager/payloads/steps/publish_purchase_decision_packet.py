from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(
        fields={
            **inputs("audit_purchase_recommendation", "audited_recommendation"),
            "case_assessment": upstream("assess_procurement_case", "case_assessment"),
        }
    ),
    flow=agent("purchase_report_writer"),
    output=OutputSpec(fields={"purchase_decision_packet": flow_output()}),
)
