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
    candidate_count = int(artifact.get("candidate_count") or 0)
    artifact.setdefault(
        "executive_summary",
        (
            f"Prepared {candidate_count} computational candidate evaluation(s) "
            "for human scientific review."
        ),
    )
    artifact.setdefault("confidence", 0.25)
    artifact.setdefault(
        "evidence",
        [
            {
                "type": "continuous_discovery_cycle_evaluations",
                "candidate_count": candidate_count,
                "source_ref": "discovery_service_review.json",
            }
        ],
    )
    artifact.setdefault(
        "next_steps",
        [
            "Review the ranked computational candidates and source cycle artifacts.",
            "Obtain independent binding, selectivity, ADMET, and toxicity evidence before any downstream action.",
        ],
    )
    artifact.setdefault(
        "source_refs",
        [
            "inputs.json",
            "events.jsonl",
            "result.json",
            "service_state.json",
            "cycle_progress.json",
            "discovery_service_review.json",
        ],
    )
    output = Path(ctx["output_folder"])
    output.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(artifact, indent=2, sort_keys=True) + "\n"
    (output / "final_artifact.json").write_text(serialized, encoding="utf-8")
    (Path(ctx["run_dir"]) / "final_artifact.json").write_text(
        serialized, encoding="utf-8"
    )
    state["final_report"] = artifact
    write_discovery_state(ctx, state)
    return {
        "final_artifact": artifact,
        "output_files": [str(output / "final_artifact.json")],
    }
