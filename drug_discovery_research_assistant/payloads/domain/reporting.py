"""Review-only discovery packet composition."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .native_stages import (
    read_discovery_state,
    run_stage_script,
    write_discovery_state,
)


def publish_ranking(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = read_discovery_state(ctx)
    result = run_stage_script(
        ctx,
        state,
        "stage_e.py",
        {"evaluations": state.get("evaluations") or []},
    )
    artifact = result.get("review_report") or {}
    artifact["type"] = "drug_discovery_research_packet"
    artifact.setdefault("recommended_action", "review_required")
    artifact.setdefault(
        "source_refs", ["service_state.json", "discovery_service_review.json"]
    )
    output = Path(ctx["output_folder"])
    output.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    (output / "final_artifact.json").write_text(serialized, encoding="utf-8")
    (Path(ctx["run_dir"]) / "final_artifact.json").write_text(
        serialized, encoding="utf-8"
    )
    write_discovery_state(ctx, state)
    return {
        "final_artifact": artifact,
        "output_files": [str(output / "final_artifact.json")],
    }
