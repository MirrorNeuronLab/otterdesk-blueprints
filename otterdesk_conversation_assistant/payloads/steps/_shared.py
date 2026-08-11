from mn_sdk.step_graph import run_input, upstream


def inputs(*, previous_step: str = ""):
    fields = {"payload": run_input("payload")}
    if previous_step:
        fields[f"{previous_step}_result"] = upstream(previous_step)
    return fields

