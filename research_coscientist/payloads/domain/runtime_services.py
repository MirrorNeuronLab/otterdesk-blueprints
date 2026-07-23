"""Runtime-boundary adapters for Research Co-Scientist."""

from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context

from .common import BLUEPRINT_ID


def runtime_context_for_step(
    *, inputs: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
    runs_root: str | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    return create_blueprint_run_context(
        runtime_file=__file__, blueprint_id=BLUEPRINT_ID,
        inputs=inputs, config=config, runs_root=runs_root, run_id=run_id,
    ).to_mapping()


__all__ = ["runtime_context_for_step"]
