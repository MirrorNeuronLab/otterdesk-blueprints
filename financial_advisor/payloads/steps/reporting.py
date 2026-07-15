from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from runtime import runtime
from ._shared import execute


OPERATIONS = {
    "audit": runtime.step_advisor_review_auditor,
    "report": runtime.step_financial_advice_reporter,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown financial reporting operation: {operation}") from exc
