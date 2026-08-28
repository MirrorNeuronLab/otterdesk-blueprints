from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = ""):
    fields = {
        "disease_or_target_profile": run_input("disease_or_target_profile"),
        "assay_constraints": run_input("assay_constraints"),
        "candidate_seed_set": run_input("candidate_seed_set"),
        "literature_corpus": run_input("literature_corpus"),
        "screening_criteria": run_input("screening_criteria"),
        "input_folder": run_input("input_folder"),
        "output_folder": run_input("output_folder"),
    }
    if previous_step:
        fields["previous"] = upstream(previous_step)
    return fields
