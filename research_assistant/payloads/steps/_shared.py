from mn_sdk.step_graph import upstream


def inputs(previous_step):
    return {"previous": upstream(previous_step, "hypothesis_analysis")}
