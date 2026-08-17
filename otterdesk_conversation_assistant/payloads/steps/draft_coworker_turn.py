from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs(previous_step="prepare_conversation_context")),
    flow=agent("coworker_conversation_proxy"),
    output=OutputSpec(fields={"coworker_turn": flow_output()}),
)
