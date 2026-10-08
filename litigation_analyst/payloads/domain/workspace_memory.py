"""Membrane navigation for published findings; immutable originals remain evidence authority."""
import os
import json
from pathlib import Path

from mn_sdk.text_memory import runtime_text_memory
from mn_context_engine_sdk.intelligent_system import RuntimeRecord
from mn_temporal_graph_skill import fingerprint

from .claim_memory import _notes
from .round_state import save


def publish(context, workspace):
    scope = {"job_id": context.get("job_id") or os.environ.get("MN_JOB_ID"),
        "run_id": context.get("run_id") or os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID")}
    memory = runtime_text_memory(context["config"], principal="round-specialists", scope=scope)
    if memory is None:
        return {"status": "Disabled by configuration"}
    try:
        receipts = []
        catalog = json.loads((Path(context["run_dir"]) / "case/source-query.json").read_text())
        for finding in workspace["findings"]:
            identifier = "case-finding-" + fingerprint([scope, workspace["matter_id"], finding["id"], finding["material_digest"]])
            relations = tuple((identifier, relation, "case-evidence-" + fingerprint([scope, workspace["matter_id"], evidence_id]))
                for relation, ids in (("SUPPORTED_BY", finding["supporting_evidence"]), ("OPPOSED_BY", finding["counter_evidence"]))
                for evidence_id in ids)
            record = RuntimeRecord(identifier, finding["title"], workspace["captured_at"],
                "inferred_assessment_not_legal_evidence", {"memory_family": "litigation_workspace",
                    "case_snapshot": workspace["snapshot_id"], "finding_id": finding["id"],
                    "finding_revision": finding["revision"], "review_state": finding["review_state"],
                    "clock_basis": "investigation_capture_not_source_event"},
                notes=_notes({"assessment": finding["assessment"], "limitations": finding["limitations"],
                    "counter_evidence": finding["counter_evidence"], "gap_ids": finding["gap_ids"],
                    "source_ref": "case/workspace.json", "qualification": "Historical navigation only; re-read exact originals before citation"}),
                relations=relations, kind="hypothesis")
            receipts.append(memory.record(record, event_id=["case-workspace-finding", identifier],
                upstream=[{"source_ref": "case/workspace.json"}], allow=["round-specialists"]))
        required = {identifier for finding in workspace["findings"] for identifier in
                    finding["supporting_evidence"] + finding["counter_evidence"]}
        for evidence in workspace["evidence"]:
            if evidence["evidence_id"] not in required:
                continue
            identifier = "case-evidence-" + fingerprint([scope, workspace["matter_id"], evidence["evidence_id"]])
            record = RuntimeRecord(identifier, "Case source locator", workspace["captured_at"],
                "source_navigation_not_case_evidence", {"memory_family": "litigation_workspace_locator",
                    "case_snapshot": workspace["snapshot_id"], "clock_basis": "investigation_capture_not_source_event"},
                notes=_notes({**{k: evidence[k] for k in ("evidence_id", "source_id", "content_sha256", "start_offset", "end_offset")},
                    "source_reference": catalog["source_records"][evidence["source_id"]]}),
                relations=((identifier, "CITES", "case-source-" + fingerprint([workspace["matter_id"], evidence["source_id"]])),))
            receipts.append(memory.record(record, event_id=["case-workspace-locator", identifier, workspace["snapshot_id"]],
                upstream=[{"source_ref": "case/workspace.json"}], allow=["round-specialists"]))
        receipt = {"status": "Published", "qualification": "Membrane authored graph navigation; frozen source corpus is evidence authority",
                   "receipts": receipts}
        save(context["run_dir"], "case/workspace_memory.json", receipt)
        return {"status": receipt["status"], "qualification": receipt["qualification"]}
    finally:
        memory.close()
