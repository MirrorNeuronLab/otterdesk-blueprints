from __future__ import annotations

from typing import Any, Callable

from mn_sdk.step_runtime import StepContext, find_message_payload

import run_blueprint as runtime


def execute(context: StepContext, handler: Callable[..., dict[str, Any]], **options: Any) -> dict[str, Any]:
    options.setdefault(
        "inputs",
        find_message_payload(
            context.message,
            required_keys=frozenset(
                {
                    "document_folder",
                    "input_folder",
                    "output_folder",
                    "portfolio",
                    "tax_year",
                    "filing_status",
                    "monitoring",
                }
            ),
        ),
    )
    return runtime.execute_runtime_handler(
        context.step_id,
        handler,
        config=context.config or None,
        run_id=context.run_id or None,
        **options,
    )
