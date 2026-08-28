"""Runtime-boundary adapter; domain processing stays in focused modules."""

from __future__ import annotations

from typing import Any

from mn_sdk.blueprint_support import create_blueprint_run_context

from .common import BLUEPRINT_ID


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
    if not str(payload.get("input_folder") or "").strip() and not str(payload.get("github_repo_url") or "").strip():
        configured_inputs = (
            ((base.config.get("inputs") or {}).get("payload") or {})
            if isinstance(base.config, dict)
            else {}
        )
        configured_folder = str(configured_inputs.get("input_folder") or "").strip()
        if configured_folder and not configured_folder.startswith("@/"):
            # `local_inputs` rewrites the bundle-relative default into the
            # platform's mounted, read-only source snapshot before this worker
            # starts. Prefer that authoritative runtime path.
            payload["input_folder"] = configured_folder
        else:
            # Direct Python invocation does not run launch-time local-input
            # staging, so retain a deterministic bundled fixture for tests.
            payload["input_folder"] = str(base.layout.root / "examples" / "sample_inputs")
    return base.to_mapping()
