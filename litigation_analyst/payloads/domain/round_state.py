"""Immutable litigation round artifacts and the existing review projection."""
import hashlib
import json
import time
from pathlib import Path

from mn_prototype_bounded_tool_loop_agent.checkpoint import atomic_json
from mn_sdk.blueprint_support import source_manifest
from mn_sdk.step_runtime import artifact_reference
from .indexing import validate_indexes
from .evidence.store import EvidenceStore


def read(path):
    return json.loads(Path(path).read_text())


def save(root, name, value):
    path = Path(root) / name
    if path.exists() and read(path) != value:
        raise ValueError("Committed litigation artifact changed: " + name)
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, value)
    return {"path": name, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}


def load(root, ref):
    root = Path(root).resolve()
    path = (root / ref["path"]).resolve()
    if not path.is_relative_to(root) or hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
        raise ValueError("Committed litigation artifact path or hash mismatch")
    return read(path)


def open_round(context, work):
    root = Path(context["run_dir"])
    frozen = load(root, work["context"])
    if frozen["config"] != context["config"]:
        raise ValueError("Investigation configuration changed")
    return root, frozen


def task_input(context, work):
    root, frozen = open_round(context, work)
    return root, frozen, load(root, work["task"])


def initialize(context, *, llm_client=None):
    root = Path(context["run_dir"])
    case = root / "case"
    corpus, receipt = validate_indexes(case, context["config"]["investigation"]["access_scope"])
    descriptor = source_manifest(__file__)["workflow"]["child_workflows"]["investigate_case_evidence"]
    cfg = context["config"]["dynamic_investigation"]
    if not 1 <= cfg["max_rounds"] <= descriptor["max_rounds"] or not 1 <= cfg["hypotheses_per_round"] <= 2:
        raise ValueError("Dynamic investigation exceeds the admitted workflow bounds")
    store = EvidenceStore(case / "evidence.sqlite3")
    store.add_sources(corpus.scan())
    existing = store.query_readonly("SELECT id FROM investigations ORDER BY id")
    identifier = existing[0]["id"] if existing else store.create_investigation(
        context["payload"]["goal"], corpus.access_scope, llm_model="default", graph_path=case / "evidence.rgx")
    name = "case/rounds/context.json"
    if not (root / name).exists():
        save(root, name, {"config": context["config"], "payload": context["payload"],
            "investigation_id": identifier, "indexes": receipt,
            "deadline": time.time() + context["config"]["investigation"]["max_investigation_seconds"],
            "source_review_flags": {d.source_id: "Potential privileged material; human handling review required."
                for d in corpus.scan() if d.text and any(t in d.text.lower() for t in (
                    "attorney-client privileged", "seeking legal representation", "seeking legal advice", "request for legal representation"))}})
    frozen = read(root / name)
    if frozen["indexes"] != receipt or frozen["config"] != context["config"] or frozen["payload"] != context["payload"]:
        raise ValueError("Investigation binding changed")
    ref = save(root, name, frozen)
    return {"context": ref, "status": "planning"}, [artifact_reference("investigation_context", name)]


def checkpoint(root, frozen):
    records, hypotheses, findings, accepted, issues, follow = [], {}, {}, set(), [], []
    latest = {}
    for path in sorted((root / "case/rounds").glob("r*-evidence.json")):
        records.extend(read(path)["records"])
    for path in sorted((root / "case/rounds").glob("r*-assessment.json")):
        value = read(path)
        latest[value["hypothesis"]["id"]] = value
    for value in latest.values():
        hypotheses[value["hypothesis"]["id"]] = value["hypothesis"]
        for f in value["report"]["findings"]:
            findings[f["id"]] = f
        follow.extend(value["report"]["follow_up"])
    for path in sorted((root / "case/rounds").glob("r*-review.json")):
        value = read(path)
        accepted.update(value["accepted_ids"])
        issues.extend(value["issues"])
    accepted.intersection_update(findings)
    return {"mode": "dynamic_subworkflow", "records": records, "stop_reason": "round_completed", "data": {
        "investigation_id": frozen["investigation_id"], "hypotheses": hypotheses,
        "source_review_flags": frozen["source_review_flags"], "derivations": [],
        "report_draft": {"findings": list(findings.values()), "conclusion_ids": sorted(accepted), "follow_up": list(dict.fromkeys(follow))},
        "report_review": {"accepted_ids": sorted(accepted), "issues": list(dict.fromkeys(issues))}}}


def finish(root, frozen, reason):
    from .app.review import build_review
    state = checkpoint(root, frozen)
    state["stop_reason"] = reason
    atomic_json(root / "case/agent_checkpoint.json", state)
    summary = build_review(state, EvidenceStore(root / "case/evidence.sqlite3"), frozen["payload"]["goal"])
    atomic_json(root / "case/investigation.json", summary)
    return {"investigation": artifact_reference("investigation", "case/investigation.json"),
            "audit_database": artifact_reference("evidence_database", "case/evidence.sqlite3"), "stop_reason": reason}
