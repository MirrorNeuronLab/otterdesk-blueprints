from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime


def run(context: StepContext) -> dict:
    return runtime.run_runtime_step(context.step_id, context=context)
