from mn_sdk.step_graph import run_input, upstream


def inputs(*aspect_keys: str, previous_step: str = ""):
    keys = (
        "business_goal",
        "goal_id",
        "input_folder",
        "output_folder",
        "peer_mcp_servers",
        "email_send_approval",
        *aspect_keys,
    )
    fields = {key: run_input(key) for key in keys}
    if previous_step:
        fields[f"{previous_step}_result"] = upstream(previous_step)
    return fields
