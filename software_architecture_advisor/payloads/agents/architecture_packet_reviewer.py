"""Thin binding for an admitted immutable OpenShell review."""
from mn_sdk.step_runtime import receive_input, send_output
from mn_prototype_stateful_step_agent import require_child_step_input
from domain.sandbox_review import review_admitted


def run(context):
    work = require_child_step_input(receive_input(context))
    result = review_admitted(work['review_input'])
    return send_output(result, artifacts=[result['result']])
