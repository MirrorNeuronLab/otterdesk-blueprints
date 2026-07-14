from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._shared import execute


OPERATIONS = {
    "public_finance": runtime.step_public_finance_researcher,
    "reconcile": runtime.step_advisor_evidence_reconciler,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown finance research operation: {operation}") from exc
