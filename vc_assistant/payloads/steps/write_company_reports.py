from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("audit_valuation_analysis", "audited_analysis")
    ),
    flow=agent("company_report_writer"),
    output=OutputSpec(fields={"company_reports": flow_output()}),
)
