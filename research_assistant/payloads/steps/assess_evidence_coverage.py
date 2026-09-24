from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("build_research_evidence")),
    flow=agent("research_evidence_reviewer"),
    output=OutputSpec(fields={"evidence_coverage": flow_output()}),
)
