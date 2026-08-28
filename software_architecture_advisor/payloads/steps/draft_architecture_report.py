from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs

STEP = StepSpec(
    input=InputSpec(fields=inputs("author_implementation_prompts")),
    flow=agent("architecture_report_writer"),
    output=OutputSpec(fields={"report_draft": flow_output()}),
)
