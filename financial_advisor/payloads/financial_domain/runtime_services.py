"""Runtime-boundary adapters for Financial Advisor."""

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
    """Create the route-neutral context used by the shared agent prototype.

    Financial domain handlers persist their own ``workflow_state/state.json``.
    Keeping that state out of the generic context prevents the outer prototype
    lifecycle from writing a stale copy over the domain's transactional update.
    """

    return create_blueprint_run_context(
        runtime_file=workflow.__file__,
        blueprint_id=workflow.BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    ).to_mapping()


append_event = workflow.append_event

__all__ = ["append_event", "runtime_context_for_step"]
