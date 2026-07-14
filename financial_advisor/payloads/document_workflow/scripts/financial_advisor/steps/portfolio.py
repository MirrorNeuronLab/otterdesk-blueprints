from __future__ import annotations

from typing import Any

from mn_sdk.step_runtime import StepContext

import run_blueprint as runtime
from ._shared import execute


OPERATIONS = {
    "load_context": runtime.step_portfolio_context_loader,
    "load_market_data": runtime.step_portfolio_market_data_loader,
    "risk": runtime.step_portfolio_risk_engine,
    "review": runtime.step_portfolio_llm_reviewer,
}


def run(context: StepContext, operation: str, **options: Any) -> dict[str, Any]:
    try:
        return execute(context, OPERATIONS[operation], **options)
    except KeyError as exc:
        raise ValueError(f"unknown portfolio operation: {operation}") from exc
