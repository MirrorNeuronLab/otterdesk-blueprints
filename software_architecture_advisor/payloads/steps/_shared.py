"""Route-neutral source and upstream mappings for advisory steps."""

from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = ""):
    fields = {
        "input_folder": run_input("input_folder"),
        "github_repo_url": run_input("github_repo_url"),
        "branch": run_input("branch"),
        "analysis_focus": run_input("analysis_focus"),
        "output_folder": run_input("output_folder"),
    }
    if previous_step:
        fields["previous"] = upstream(previous_step)
    return fields
