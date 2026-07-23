from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("reconcile_legal_review")),
    flow=agent("legal_reporter"),
    output=OutputSpec(fields={"legal_review_packet": flow_output()}),
)
