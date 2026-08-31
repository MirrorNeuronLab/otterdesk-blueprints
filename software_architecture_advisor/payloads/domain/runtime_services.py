"""Runtime-boundary adapter; domain processing stays in focused modules."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context

from .common import BLUEPRINT_ID


def _staged_input_folder(config: dict[str, Any]) -> str:
    """Return this blueprint's mounted source snapshot, when present.

    Submission preparation puts declared local inputs under ``MN_JOB_INPUT_DIR``.
    Some message invocations include the original CLI configuration as their
    overlay, which can replace the rewritten config value with a host-only
    path.  The mounted declared input is authoritative inside the worker.
    """

    input_root = str(os.environ.get("MN_JOB_INPUT_DIR") or "").strip()
    if not input_root:
        return ""
    local_inputs = config.get("local_inputs") if isinstance(config, dict) else {}
    folders = local_inputs.get("folders") if isinstance(local_inputs, dict) else []
    for spec in folders if isinstance(folders, list) else []:
        if not isinstance(spec, dict) or spec.get("config_path") != "inputs.payload.input_folder":
            continue
        relative_path = str(spec.get("runtime_path") or spec.get("payload_path") or "").strip()
        relative = Path(relative_path)
        if not relative_path or relative.is_absolute() or ".." in relative.parts:
            continue
        candidate = Path(input_root) / relative
        if candidate.is_dir():
            return str(candidate)
    return ""


def runtime_context_for_step(*, inputs: dict[str, Any] | None = None, config: dict[str, Any] | None = None, runs_root: str | None = None, run_id: str | None = None) -> dict[str, Any]:
    base = create_blueprint_run_context(
        runtime_file=__file__,
        blueprint_id=BLUEPRINT_ID,
        inputs=inputs,
        config=config,
        runs_root=runs_root,
        run_id=run_id,
    )
    payload = base.payload
    staged_folder = _staged_input_folder(base.config)
    configured_inputs = (
        ((base.config.get("inputs") or {}).get("payload") or {})
        if isinstance(base.config, dict)
        else {}
    )
    configured_folder = str(configured_inputs.get("input_folder") or "").strip()
    if staged_folder:
        payload["input_folder"] = staged_folder
    elif configured_folder:
        # Submission preparation stages the host folder and rewrites this
        # value to its worker-visible path. A route-neutral message can still
        # retain the original host path, which must never reach DockerWorker.
        payload["input_folder"] = configured_folder
    return base.to_mapping()
