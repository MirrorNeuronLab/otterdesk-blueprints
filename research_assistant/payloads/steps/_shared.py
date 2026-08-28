from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = ""):
    fields = {
        "research_goal": run_input("research_goal"),
        "research_question": run_input("research_question"),
        "research_domain": run_input("research_domain"),
        "scope": run_input("scope"),
        "success_criteria": run_input("success_criteria"),
        "constraints": run_input("constraints"),
        "seed_hypotheses": run_input("seed_hypotheses"),
        "input_folder": run_input("input_folder"),
        "output_folder": run_input("output_folder"),
    }
    if previous_step:
        fields["previous"] = upstream(previous_step)
    return fields
