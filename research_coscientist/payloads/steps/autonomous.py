from mn_sdk.step_runtime import StepContext

from runtime import runtime


def run(context: StepContext) -> dict:
    return runtime.run_runtime_step(context.step_id, context=context)
