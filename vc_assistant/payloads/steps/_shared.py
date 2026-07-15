from __future__ import annotations

from mn_sdk.step_graph import run_input, upstream


def step_inputs(previous_step: str = "", previous_field: str = ""):
    fields = {
        "document_folder": run_input("document_folder"),
        "output_folder": run_input("output_folder"),
        "monitoring": run_input("monitoring"),
        "force_reprocess": run_input("force_reprocess"),
    }
    if previous_step:
        fields["previous"] = upstream(
            previous_step, *([previous_field] if previous_field else [])
        )
    return fields
