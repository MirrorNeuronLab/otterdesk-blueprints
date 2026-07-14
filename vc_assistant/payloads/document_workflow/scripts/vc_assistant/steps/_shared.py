from __future__ import annotations

from typing import Any, Callable

from mn_sdk.step_runtime import StepContext, find_message_payload

from blueprint_runtime import runtime


def execute(
    context: StepContext,
    handler: Callable[..., dict[str, Any]],
    *,
    inputs: dict[str, Any] | None = None,
    runs_root: str | None = None,
    llm_client: Any | None = None,
) -> dict[str, Any]:
    if inputs is None:
        inputs = find_message_payload(
            context.message,
            required_keys=frozenset(
                {
                    "document_folder",
                    "input_folder",
                    "output_folder",
                    "monitoring",
                    "force_reprocess",
                }
            ),
        )
    return runtime.execute_runtime_handler(
        context.step_id,
        handler,
        inputs=inputs,
        config=context.config or None,
        runs_root=runs_root,
        run_id=context.run_id or None,
        llm_client=llm_client,
    )
