from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import inputs


STEP = StepSpec(
    input=InputSpec(fields=inputs()),
    flow=agent("otterdesk_conversation_assistant"),
    output=OutputSpec(fields={"prepared_context": flow_output()}),
)
