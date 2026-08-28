from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("frame_research_problem")),
    flow=agent("research_evidence_curator"),
    output=OutputSpec(fields={"research_evidence": flow_output()}),
)
