from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from runtime import runtime
from ._shared import execute


OPERATIONS = {
    "watch": runtime.step_financial_folder_watcher,
    "read": runtime.step_financial_document_reader,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown financial intake operation: {operation}") from exc
