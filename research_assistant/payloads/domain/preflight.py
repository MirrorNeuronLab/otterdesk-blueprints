"""Independent, deterministic research preflight assessments."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .state import _state


def _write(ctx: dict[str, Any], name: str, assessment: dict[str, Any]) -> dict[str, Any]:
    folder = Path(ctx["run_dir"]) / "workflow_state"
    folder.mkdir(parents=True, exist_ok=True)
    target = folder / f"{name}.json"
    temporary = folder / f".{name}.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(assessment, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    return {"branch_artifact": {"name": name, "path": f"workflow_state/{name}.json"}, "status": assessment["status"]}


def assess_evidence_coverage(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    evidence = (_state(ctx).get("evidence") or {})
    refs = sorted(set(evidence.get("source_refs") or []))
    gaps = [str(item)[:500] for item in (evidence.get("evidence_gaps") or [])[:20]]
    assessment = {
        "kind": "evidence_coverage",
        "status": "ready_for_hypothesis_review" if evidence.get("usable_evidence_present") else "needs_evidence",
        "source_refs": refs,
        "gaps": gaps,
        "usable_local_document_count": int(evidence.get("usable_local_document_count") or 0),
        "usable_public_source_count": int(evidence.get("usable_public_source_count") or 0),
        "limitation": "Source relevance does not validate a hypothesis or authorize an experiment.",
    }
    return _write(ctx, "evidence_coverage", assessment)


def assess_experiment_readiness(ctx: dict[str, Any], **_options: Any) -> dict[str, Any]:
    state = _state(ctx)
    inputs = state.get("inputs") or {}
    evidence = state.get("evidence") or {}
    candidates = inputs.get("seed_hypotheses") or []
    if not isinstance(candidates, list):
        candidates = []
    data = [item for item in (state.get("documents") or []) if str(item.get("name") or "").lower().endswith(".csv")]
    assessment = {
        "kind": "experiment_readiness",
        "status": "planning_only",
        "seed_hypothesis_count": len(candidates),
        "local_csv_count": len(data),
        "evidence_available": bool(evidence.get("usable_evidence_present")),
        "missing_for_execution": [
            "approved exact experiment batch and code digest",
            "declared calibration and evaluation data roles",
            "bounded numerical execution grant",
        ],
        "limitation": "This assessment prepares a plan; it does not grant execution authority.",
    }
    return _write(ctx, "experiment_readiness", assessment)


def load_preflight(run_dir: str | Path) -> dict[str, dict[str, Any]]:
    folder = Path(run_dir) / "workflow_state"
    result = {}
    for name in ("evidence_coverage", "experiment_readiness"):
        path = folder / f"{name}.json"
        if not path.is_file():
            raise FileNotFoundError(f"Required research preflight artifact missing: {path}")
        item = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(item, dict) or item.get("kind") != name:
            raise ValueError(f"Invalid research preflight artifact: {name}")
        result[name] = item
    return result
