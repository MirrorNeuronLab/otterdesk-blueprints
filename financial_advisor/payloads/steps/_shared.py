from __future__ import annotations

from typing import Any, Callable

from mn_sdk.blueprint_support import StepLifecycleHooks, execute_step_handler
from mn_sdk.step_runtime import StepContext, find_message_payload

from runtime import runtime


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
    llm_client = options.pop("llm_client", None)

    def context_factory(**context_options: Any) -> dict[str, Any]:
        return runtime.runtime_context_for_step(**context_options, llm_client=llm_client)

    return execute_step_handler(
        context.step_id,
        handler,
        context_factory=context_factory,
        config=context.config or None,
        runs_root=options.pop("runs_root", None),
        run_id=context.run_id or None,
        inputs=options.pop("inputs", None),
        llm_client=llm_client,
        hooks=StepLifecycleHooks(
            append_event=runtime.append_event,
            append_debug=getattr(runtime, "append_debug_record", None),
            write_benchmark=getattr(runtime, "write_benchmark_artifacts", None),
        ),
    )
