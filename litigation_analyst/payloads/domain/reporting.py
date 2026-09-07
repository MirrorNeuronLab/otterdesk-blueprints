"""Verify exact evidence before writing the customer-facing draft and review index."""

import json
from pathlib import Path

from mn_sdk.step_runtime import artifact_reference
from .evidence.store import EvidenceStore
from .intake import PreparedCorpus


def write_review(context, *, llm_client=None):
    run_dir = Path(context["run_dir"])
    case = run_dir / "case"
    summary = json.loads((case / "investigation.json").read_text())
    report = summary["report"]
    if report["status"] != "draft_for_human_review":
        raise ValueError("only human-review drafts may be written")
    corpus = PreparedCorpus(case, context["config"]["investigation"]["access_scope"])
    documents = {d.source_id: d for d in corpus.scan()}
    evidence = EvidenceStore(case / "evidence.sqlite3").evidence_for(
        report["investigation_id"]
    )
    for e in evidence:
        source = documents.get(e.source_id)
        if (
            source is None
            or source.text is None
            or source.content_sha256 != e.content_sha256
            or source.text[e.start_offset : e.end_offset] != e.text
        ):
            raise ValueError(
                "draft citation does not resolve to the frozen source snapshot"
            )
    if set(report["evidence_ids"]) != {e.evidence_id for e in evidence}:
        raise ValueError("draft evidence list differs from its audit record")
    inventory = json.loads((case / "source_inventory.json").read_text())
    text = report["markdown"] + "\n\n## Source coverage\n\n"
    text += f"{inventory['readable_count']} of {inventory['document_count']} source records had readable text. "
    text += "See case/source_inventory.json for original file hashes and unprocessed sources. "
    text += "Citations address the frozen normalized text in case/sources.json; mailbox spans address normalized message headers and bodies.\n"
    (run_dir / "review_draft.md").write_text(text, encoding="utf-8")
    index = {
        "status": report["status"],
        "report": "review_draft.md",
        "audit_database": "case/evidence.sqlite3",
        "source_inventory": "case/source_inventory.json",
        "normalized_sources": "case/sources.json",
        "agent_checkpoint": "case/agent_checkpoint.json",
        "stop_reason": summary["stop_reason"],
        "actual_devices": summary["actual_devices"],
        "failed_queries": summary["failed_queries"],
        "hypothesis_count": summary["hypothesis_count"],
        "unreadable_count": len(inventory["unreadable_sources"]),
    }
    (run_dir / "review_index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )
    refs = [
        artifact_reference("review_draft", "review_draft.md"),
        artifact_reference("review_index", "review_index.json"),
    ]
    return {
        "review_draft": refs[0],
        "review_index": refs[1],
        "status": report["status"],
    }, refs
