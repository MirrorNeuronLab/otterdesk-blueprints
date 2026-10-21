"""Independent, deterministic research preflight assessments."""

from __future__ import annotations

from typing import Any

from .state import read_state
from .common import BLUEPRINT_ID


def _write(block, name, assessment, evidence):
    reference = block.store.commit(f"workflow_state/{name}.json", assessment, kind="research_preflight")
    return {"assessment": reference.to_dict(), "evidence": evidence, "status": assessment["status"]}


def assess_evidence_coverage(block, inputs) -> dict[str, Any]:
    evidence = (read_state(block, inputs["previous"]).get("evidence") or {})
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
    return _write(block, "evidence_coverage", assessment, inputs["previous"]["state"])


def assess_experiment_readiness(block, inputs) -> dict[str, Any]:
    previous = inputs["previous"]
    state = read_state(block, previous)
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
    return _write(block, "experiment_readiness", assessment, previous["state"])


def load_preflight(block, branches):
    names = ("evidence_coverage", "experiment_readiness")
    source = branches[names[0]]["evidence"]
    if branches[names[1]]["evidence"] != source:
        raise ValueError("Research preflight branches describe different evidence snapshots")
    result = {}
    for name in names:
        item = block.store.read(branches[name]["assessment"])
        if not isinstance(item, dict) or item.get("kind") != name:
            raise ValueError(f"Invalid research preflight artifact: {name}")
        result[name] = item
    return read_state(block, {"state": source}), result
