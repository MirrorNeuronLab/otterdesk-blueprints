from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("build_purchase_evidence", "purchase_evidence")),
    flow=agent("purchase_case_assessor"),
    output=OutputSpec(fields={"case_assessment": flow_output()}),
)
