from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("metrics_file", previous_step="calculate_unit_economics")),
    flow=agent("business_finance_controller"),
    output=OutputSpec(fields={"financial_control_packet": flow_output()}),
)

