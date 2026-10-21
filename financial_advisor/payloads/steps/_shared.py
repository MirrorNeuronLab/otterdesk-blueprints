"""Financial phase boundaries; specialist collaboration remains in StepSpec."""
from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step="", output=""):
    return {"previous": upstream(previous_step, output)} if previous_step else {"request": run_input()}
