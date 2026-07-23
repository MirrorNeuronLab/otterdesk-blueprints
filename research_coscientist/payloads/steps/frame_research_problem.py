from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs()),
    flow=agent("research_goal_framer"),
    output=OutputSpec(fields={"research_problem": flow_output()}),
)
