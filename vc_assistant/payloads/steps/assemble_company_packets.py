from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output

from ._shared import step_inputs


STEP = StepSpec(
    input=InputSpec(
        fields=step_inputs("detect_packet_changes", "packet_changes")
    ),
    flow=agent("company_packet_grouper"),
    output=OutputSpec(fields={"company_packets": flow_output()}),
)
