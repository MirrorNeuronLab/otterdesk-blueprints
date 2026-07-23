from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("reconcile_advisor_evidence")),
    flow=agent("financial_advice_reporter"),
    output=OutputSpec(fields={"financial_review_packet": flow_output()}),
)
