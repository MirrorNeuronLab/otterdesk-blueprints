from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(
    input=InputSpec(fields=inputs("draft_architecture_report")),
    flow=agent("architecture_advice_auditor"),
    output=OutputSpec(fields={"audit": flow_output()}),
)
