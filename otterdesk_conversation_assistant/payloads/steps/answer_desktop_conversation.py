from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs(previous_step="draft_coworker_turn")),
    flow=agent("otterdesk_conversation_assistant"),
    output=OutputSpec(fields={"conversation_reply": flow_output()}),
)
