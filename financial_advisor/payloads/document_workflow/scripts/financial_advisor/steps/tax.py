from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._shared import execute


OPERATIONS = {
    "route": runtime.step_tax_document_router,
    "ocr": runtime.step_tax_form_ocr_capturer,
    "prepare": runtime.step_tax_workpaper_preparer,
    "review": runtime.step_tax_llm_reviewer,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown tax operation: {operation}") from exc
