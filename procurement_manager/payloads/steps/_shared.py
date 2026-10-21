from mn_sdk.step_graph import upstream


def inputs(previous_step, previous_field):
    return {"previous": upstream(previous_step, previous_field)}
