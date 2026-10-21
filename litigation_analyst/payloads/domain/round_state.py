"""Immutable litigation round artifacts and the existing review projection."""

from mn_sdk.agent_events import activity_operation
import json
import os
import time
from pathlib import Path

from mn_sdk.blueprint_support import source_manifest
from mn_sdk.committed_artifacts import (
    CommittedArtifactConflict,
    CommittedArtifactError,
    CommittedJsonStore,
)
from .indexing import validate_indexes
from .evidence.store import EvidenceStore
from .handling import review_flags
from .matter_intake import load as load_matter
from .review_scope import limits


def read(path):
    return json.loads(Path(path).read_text())


def save(root, name, value):
    try:
        committed = CommittedJsonStore(root).commit(name, value)
    except CommittedArtifactConflict as error:
        raise ValueError("Committed litigation artifact changed: " + name) from error
    return committed.to_dict()


def load(root, ref):
    store = CommittedJsonStore(root)
    try:
        return store.read(ref)
    except (CommittedArtifactError, OSError) as error:
        raise ValueError("Committed litigation artifact path or hash mismatch") from error


def open_round(context, reference):
    from .state import read_indexed
    root = context.store.run_dir
    if reference.get("path") != "case/rounds/context.json":
        raise ValueError("Investigation requires its admitted case context")
    frozen = load(root, reference)
    if (frozen["config"] != context.original_config or frozen["memory_scope"] != {
            "job_id": context.job_id or os.environ.get("MN_JOB_ID"),
            "run_id": context.run_id or os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID")}):
        raise ValueError("Investigation configuration changed")
    read_indexed(context, frozen["indexed"])
    return root, frozen


def task_input(context, work):
    packet = work["task"]
    root, frozen = open_round(context, packet["context"])
    return root, frozen, load(root, packet["task"])


@activity_operation('Preparing the case investigation', completed='Preparing the case investigation: completed')
def initialize(context, inputs):
    from .state import read_indexed
    indexed = inputs["previous"]["result"]["evidence"]
    _, captured = read_indexed(context, indexed)
    payload = captured["inputs"]
    root = context.store.run_dir
    case = root / "case"
    corpus, receipt = validate_indexes(case, context.config["investigation"]["access_scope"])
    descriptor = source_manifest(__file__)["workflow"]["child_workflows"]["investigate_case_evidence"]
    cfg = limits(context.original_config)
    if not 1 <= cfg["max_rounds"] <= descriptor["max_rounds"] or not 1 <= cfg["hypotheses_per_round"] <= 2:
        raise ValueError("Dynamic investigation exceeds the admitted workflow bounds")
    store = EvidenceStore(case / "evidence.sqlite3")
    store.add_sources(corpus.scan())
    existing = store.query_readonly("SELECT id FROM investigations ORDER BY id")
    identifier = existing[0]["id"] if existing else store.create_investigation(
        payload["goal"], corpus.access_scope, llm_model="default", graph_path=case / "evidence.rgx")
    name = "case/rounds/context.json"
    if not (root / name).exists():
        save(root, name, {"config": context.original_config, "payload": payload, "indexed": indexed,
            "memory_scope": {"job_id": context.job_id or os.environ.get("MN_JOB_ID"),
                             "run_id": context.run_id or os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID")},
            "investigation_id": identifier, "indexes": receipt,
            "deadline": time.time() + cfg["seconds"], "review_plan": cfg, "matter": load_matter(root),
            "source_review_flags": review_flags(corpus.scan(), load_matter(root)["exclusions"])})
    frozen = read(root / name)
    if frozen["indexes"] != receipt or frozen["config"] != context.original_config or frozen["payload"] != payload or frozen["indexed"] != indexed:
        raise ValueError("Investigation binding changed")
    ref = save(root, name, frozen)
    return {"context": ref, "status": "planning"}


def checkpoint(root, frozen):
    records, hypotheses, findings, accepted, issues, follow = [], {}, {}, set(), [], []
    latest = {}
    for path in sorted((root / "case/rounds").glob("r*-evidence.json")):
        records.extend(read(path)["records"])
    for path in sorted((root / "case/rounds").glob("r*-assessment.json")):
        value = read(path)
        latest[value["hypothesis"]["id"]] = value
    for value in latest.values():
        hypotheses[value["hypothesis"]["id"]] = {**value["hypothesis"], "work_items": value["work_items"], "counsel_issue_ids": value.get("counsel_issue_ids", [])}
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


def finish(context, frozen, reason, reference, revision):
    from .app.review import build_review
    from .state import terminal
    root = context.store.run_dir
    state = checkpoint(root, frozen)
    state["stop_reason"] = reason
    summary = build_review(state, EvidenceStore(root / "case/evidence.sqlite3"), frozen["payload"]["goal"])
    return terminal(context, frozen["indexed"], frozen["payload"], state, summary, context=reference, revision=revision)
