"""Logical Financial Advisor step contracts."""

from mn_sdk.step_graph import run_input, upstream


def inputs(previous_step: str = ""):
    fields = {
        "document_folder": run_input("document_folder"),
        "input_folder": run_input("input_folder"),
        "output_folder": run_input("output_folder"),
        "portfolio": run_input("portfolio"),
        "tax_year": run_input("tax_year"),
        "filing_status": run_input("filing_status"),
        "monitoring": run_input("monitoring"),
    }
    if previous_step:
        fields["previous"] = upstream(previous_step)
    return fields

