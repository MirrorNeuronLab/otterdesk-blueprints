"""Verify exact evidence before writing the customer-facing draft and review index."""

import json
import shutil
from pathlib import Path

from mn_sdk.step_runtime import artifact_reference
from .evidence.store import EvidenceStore
from .intake import PreparedCorpus
from .app.review import build_review
from .app.findings import evidence_appendix
from .app.report_sections import graph_exhibits
from mn_document_reading_skill.search import PassageIndex


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
    # Re-render from the persisted action/evidence records after citation checks.
    # A cached Markdown string is never treated as an authoritative finding.
    state = json.loads((case / "agent_checkpoint.json").read_text())
    # Recompute all derived observations from the frozen source index.
    index_reader = PassageIndex(case / "documents.sqlite3", corpus.access_scope)
    for item in state["data"].get("derivations", []):
        operation = item["arguments"]["operation"]
        if operation not in ("decode_rot13", "summarize_csv"):
            raise ValueError("unknown evidence derivation")
        actual = getattr(index_reader, operation)(**item["arguments"]["arguments"])
        if actual != item["result"]:
            raise ValueError("derived evidence differs from frozen source calculation")
    (run_dir / "evidence_appendix.md").write_text(
        evidence_appendix(evidence, state["data"].get("derivations", [])),
        encoding="utf-8",
    )
    (run_dir / "graph_appendix.md").write_text(
        "\n".join(graph_exhibits(state["records"])), encoding="utf-8"
    )
    summary = build_review(
        state, EvidenceStore(case / "evidence.sqlite3"), context["payload"]["goal"]
    )
    report = summary["report"]
    inventory = json.loads((case / "source_inventory.json").read_text())
    corpus_note = (
        "**Corpus:** Built-in EMC2 synthetic sample. This report concerns test records, not a real criminal case.\n\n"
        if inventory.get("sample")
        else ""
    )
    text = corpus_note + report["markdown"] + "\n\n## Source coverage\n\n"
    text += f"{inventory['readable_count']} of {inventory['document_count']} source records had readable text. "
    text += "See case/source_inventory.json for original file hashes and unprocessed sources. "
    text += "Citations address the frozen normalized text in case/sources.json; mailbox spans address normalized message headers and bodies.\n"
    (run_dir / "final_report.md").write_text(text, encoding="utf-8")
    index = {
        "status": report["status"],
        "report": "final_report.md",
        "evidence_appendix": "evidence_appendix.md",
        "graph_appendix": "graph_appendix.md",
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
    output = context.get("output_folder")
    if output:
        output = Path(output)
        archive = output / "runs" / run_dir.name
        if archive.resolve() != run_dir.resolve():
            if run_dir.resolve() in archive.resolve().parents:
                raise ValueError("report export must not recurse into its source run")
            archive.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(run_dir, archive, dirs_exist_ok=True)
        output.mkdir(parents=True, exist_ok=True)
        notice = f"Audit paths below are relative to `runs/{run_dir.name}/`.\n\n"
        linked_text = text.replace(
            "](evidence_appendix.md", f"](runs/{run_dir.name}/evidence_appendix.md"
        ).replace("](graph_appendix.md", f"](runs/{run_dir.name}/graph_appendix.md")
        (output / "final_report.md").write_text(notice + linked_text, encoding="utf-8")
        exported_index = {**index, "audit_root": f"runs/{run_dir.name}"}
        (output / "review_index.json").write_text(
            json.dumps(exported_index, indent=2), encoding="utf-8"
        )
    refs = [
        artifact_reference("review_draft", "final_report.md"),
        artifact_reference("review_index", "review_index.json"),
        artifact_reference("evidence_appendix", "evidence_appendix.md"),
        artifact_reference("graph_appendix", "graph_appendix.md"),
    ]
    return {
        "review_draft": refs[0],
        "review_index": refs[1],
        "status": report["status"],
    }, refs
