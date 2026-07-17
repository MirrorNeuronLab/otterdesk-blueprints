"""Runtime-boundary adapters for Legal Assistant."""

from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context

from . import workflow


def runtime_context_for_step(
    *,
    inputs: dict[str, Any] | None = None,
    config: dict[str, Any] | None = None,
    runs_root: str | None = None,
    run_id: str | None = None,
) -> dict[str, Any]:
    context = create_blueprint_run_context(
        runtime_file=workflow.__file__,
        blueprint_id=workflow.BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    return context.to_mapping()


append_event = workflow.append_event

__all__ = ["append_event", "runtime_context_for_step"]
