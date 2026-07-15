from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(fields=step_inputs("write_company_reports", "company_reports")),
    flow=agent("batch_index_writer"),
    output=OutputSpec(fields={"batch_summary": flow_output()}),
)
