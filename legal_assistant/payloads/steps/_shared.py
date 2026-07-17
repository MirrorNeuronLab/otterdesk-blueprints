from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = ""):
    fields = {
        "document_folder": run_input("document_folder"),
        "input_folder": run_input("input_folder"),
        "output_folder": run_input("output_folder"),
        "matter_profile": run_input("matter_profile"),
        "review_policy": run_input("review_policy"),
    }
    if previous_step:
        fields["previous"] = upstream(previous_step)
    return fields

