from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

from runtime import runtime
from ._shared import execute


OPERATIONS = {
    "extract": runtime.step_bank_statement_extractor,
    "normalize": runtime.step_cash_flow_normalizer,
    "analyze": runtime.step_cash_flow_llm_analyst,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown cash-flow operation: {operation}") from exc
