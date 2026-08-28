from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, sequence

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs("develop_and_challenge_hypotheses")),
    flow=sequence(
        agent("research_packet_auditor", as_="audit"),
        agent("research_report_writer", as_="publish"),
    ),
    output=OutputSpec(fields={"research_packet": flow_output()}),
)
