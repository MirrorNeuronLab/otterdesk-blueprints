"""Logical source step for the single long-lived browser simulator service."""

from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input


STEP = StepSpec(
    input=InputSpec(
        fields={
            "input_folder": run_input("input_folder"),
            "output_folder": run_input("output_folder"),
        }
    ),
    flow=agent("microduck_service"),
    output=OutputSpec(fields={"service": flow_output()}),
)
