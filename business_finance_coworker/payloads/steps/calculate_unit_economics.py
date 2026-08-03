from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("metrics_file")),
    flow=agent("bibblio_finance_controller"),
    output=OutputSpec(fields={"unit_economics_analysis": flow_output()}),
)

