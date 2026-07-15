from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from agents.batch_index_writer import run_batch_index_writer_step
from agents.company_report_writer import run_company_report_writer_step

from ._shared import execute


OPERATIONS = {
    "company": run_company_report_writer_step,
    "batch_index": run_batch_index_writer_step,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        handler = OPERATIONS[operation]
    except KeyError as exc:
        raise ValueError(f"unknown VC reporting operation: {operation}") from exc
    return execute(context, handler, **options)
