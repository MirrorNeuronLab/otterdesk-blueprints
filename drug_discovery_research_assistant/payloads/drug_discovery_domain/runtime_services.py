"""Runtime preparation for the drug-discovery specialist graph."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context


def runtime_context_for_step(
    *, inputs: dict[str, Any] | None = None, config: dict[str, Any] | None = None,
    runs_root: str | None = None, run_id: str | None = None,
) -> dict[str, Any]:
    return create_blueprint_run_context(
        runtime_file=Path(__file__).resolve().parents[1] / "runtime" / "runtime.py",
        blueprint_id="drug_discovery_research_assistant",
        inputs=inputs, config=config, runs_root=runs_root, run_id=run_id,
    ).to_mapping()
