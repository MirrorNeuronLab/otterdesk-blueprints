from __future__ import annotations

from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = "", previous_field: str = ""):
    fields = {
        "purchase_type": run_input("purchase_type"),
        "item_description": run_input("item_description"),
        "budget": run_input("budget"),
        "currency": run_input("currency"),
        "input_folder": run_input("input_folder"),
        "output_folder": run_input("output_folder"),
    }
    if previous_step:
        fields["previous"] = upstream(
            previous_step, *([previous_field] if previous_field else [])
        )
    return fields
