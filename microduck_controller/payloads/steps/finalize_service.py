"""Logical terminal step for the manually stopped Microduck service."""

from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, upstream


STEP = StepSpec(
    input=InputSpec(fields={"service": upstream("run_microduck_service")}),
    flow=agent("finalize"),
    output=OutputSpec(fields={"final_service_result": flow_output()}),
)
