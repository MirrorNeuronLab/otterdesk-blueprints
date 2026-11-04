from mn_sdk.blueprint.steps import upstream


def inputs(previous_step, previous_field):
    return {"previous": upstream(previous_step, previous_field)}
