"""Logical CT step I/O and collaboration only."""
from mn_sdk.step_graph import InputSpec, OutputSpec, StepSpec, agent, flow_output, run_input

STEP = StepSpec(
    input=InputSpec(fields={"ct_file": run_input("ct_file"), "region": run_input("region"), "prompt": run_input("prompt")}),
    flow=agent("ct_research_specialist"),
    output=OutputSpec(fields={"result": flow_output()}),
)
