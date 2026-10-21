"""Verify exact evidence before writing the customer-facing draft and review index."""

from mn_sdk.agent_events import activity_operation

import json
import os
from copy import deepcopy
from pathlib import Path

from mn_sdk.step_runtime import artifact_reference
from mn_sdk.blueprint_support.shared_outputs import copy_path_to_host
from .evidence.store import EvidenceStore
from .intake import PreparedCorpus
from .app.review import build_review
from .app.findings import evidence_appendix
from .app.report_sections import graph_exhibits


@activity_operation('Writing the litigation review', completed='Writing the litigation review: completed')
def write_review(context, inputs):
    from .state import read_terminal, file_record
    terminal = read_terminal(context, inputs["previous"]["result"])
    payload = terminal["inputs"]
    output = os.environ.get("MN_JOB_OUTPUT_DIR") or payload.get("output_folder")
    run_dir = context.store.run_dir
    case = run_dir / "case"
    summary = json.loads(context.store.path(terminal["investigation"]["path"]).read_text())
    report = summary["report"]
    if report["status"] != "draft_for_human_review":
        raise ValueError("only human-review drafts may be written")
    corpus = PreparedCorpus(case, context.config["investigation"]["access_scope"])
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
    state = json.loads(context.store.path(terminal["checkpoint"]["path"]).read_text())
    if state["data"].get("derivations"):
        raise ValueError("Retired document-index derivations require their original staged implementation")
    (run_dir / "evidence_appendix.md").write_text(
        evidence_appendix(
            [e for e in evidence if e.source_id not in state["data"].get("source_review_flags", {})],
            state["data"].get("derivations", []),
        ),
        encoding="utf-8",
    )
    (run_dir / "graph_appendix.md").write_text(
        "\n".join(graph_exhibits(state["records"])), encoding="utf-8"
    )
    from .matter_intake import load as load_matter
    from .financial_review import build as reconcile
    from .review_packets import consistency_checks
    financial = reconcile(load_matter(run_dir), tuple(documents.values()), state['data'].get('source_review_flags', {}))
    conflicts = consistency_checks(state['data'].get('report_draft', {'findings':[]}), financial)
    state = deepcopy(state)
    blocked = {c['finding_id'] for c in conflicts}
    if blocked:
        review = state['data']['report_review']
        review['accepted_ids'] = [i for i in review['accepted_ids'] if i not in blocked]
        review['issues'] += list(dict.fromkeys(c['reason'] for c in conflicts))
    (case / 'consistency_review.json').write_text(json.dumps({'checks':conflicts, 'withheld_finding_ids':sorted(blocked)}, indent=2))
    summary = build_review(
        state, EvidenceStore(case / "evidence.sqlite3"), payload["goal"]
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
    from .workspace_projection import build as build_workspace
    from .workspace_graph import attach as attach_graph
    from .workspace_history import publish as publish_history
    from .workspace_memory import publish as publish_memory
    from .workspace_web import publish as publish_web
    workspace = build_workspace(context, tuple(documents.values()), evidence, state, inventory, goal=payload["goal"])
    workspace = attach_graph(workspace, case, context.config.get("workspace", {}))
    workspace = publish_history(context, workspace, review_file=payload.get("review_file"))
    from .review_products import issue_brief, transaction_appendix
    (case / "financial_review.json").write_text(json.dumps(workspace["financial_review"], ensure_ascii=False), encoding="utf-8")
    (run_dir / "transaction_appendix.md").write_text(transaction_appendix(workspace["financial_review"]), encoding="utf-8")
    text = corpus_note + issue_brief(workspace) + '\n\n<details><summary>Advanced investigation and audit details</summary>\n\n' + text.removeprefix(corpus_note) + '\n\n</details>\n'
    from .performance import measure
    (case / 'performance.json').write_text(json.dumps(measure(run_dir), indent=2))
    (run_dir / "final_report.md").write_text(text, encoding="utf-8")
    # Memory locators refer to a durable authoritative snapshot, never a cached
    # narrative. Context-service failure is an explicit navigation limitation.
    (case / "workspace.json").write_text(json.dumps(workspace, ensure_ascii=False), encoding="utf-8")
    try:
        workspace["memory"] = publish_memory(context, workspace)
    except (OSError, ValueError, RuntimeError) as error:
        workspace["memory"] = {"status": "Unavailable", "reason": type(error).__name__,
            "qualification": "Historical workspace navigation was not published; exact frozen evidence remains available"}
    workspace_status, workspace_refs = publish_web(context, workspace)
    index = {
        "status": report["status"],
        "report": "final_report.md",
        "evidence_appendix": "evidence_appendix.md",
        "graph_appendix": "graph_appendix.md",
        "transaction_appendix": "transaction_appendix.md",
        "financial_review": "case/financial_review.json",
        "matter_intake": "case/matter.json",
        "review_plan": "case/review_plan.json",
        "audit_database": "case/evidence.sqlite3",
        "source_inventory": "case/source_inventory.json",
        "normalized_sources": "case/sources.json",
        "agent_checkpoint": "case/agent_checkpoint.json",
        "stop_reason": summary["stop_reason"],
        "actual_devices": summary["actual_devices"],
        "failed_queries": summary["failed_queries"],
        "hypothesis_count": summary["hypothesis_count"],
        "unreadable_count": len(inventory["unreadable_sources"]),
        "workspace": "case/workspace.json",
        "interactive_investigation": workspace_status.get("path"),
        "workspace_status": "workspace_status.json",
        "consistency_review": "case/consistency_review.json",
        "performance": "case/performance.json",
    }
    (run_dir / "review_index.json").write_text(
        json.dumps(index, indent=2), encoding="utf-8"
    )
    from .conversation_sources import publish_outputs
    publish_outputs(context, output_folder=output)
    if output:
        output = Path(output)
        archive = output / "runs" / run_dir.name
        if archive.resolve() != run_dir.resolve():
            if run_dir.resolve() in archive.resolve().parents:
                raise ValueError("report export must not recurse into its source run")
            archive.parent.mkdir(parents=True, exist_ok=True)
            copy_path_to_host(run_dir, archive)
        output.mkdir(parents=True, exist_ok=True)
        notice = f"Audit paths below are relative to `runs/{run_dir.name}/`.\n\n"
        linked_text = text.replace(
            "](evidence_appendix.md", f"](runs/{run_dir.name}/evidence_appendix.md"
        ).replace("](graph_appendix.md", f"](runs/{run_dir.name}/graph_appendix.md").replace("](transaction_appendix.md", f"](runs/{run_dir.name}/transaction_appendix.md")
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
        artifact_reference("transaction_appendix", "transaction_appendix.md"),
        artifact_reference("financial_review", "case/financial_review.json"),
        artifact_reference("consistency_review", "case/consistency_review.json"),
        artifact_reference("performance", "case/performance.json"),
    ] + workspace_refs + [artifact_reference("workspace_status", "workspace_status.json")]
    files = {ref["path"] for ref in refs} | {"case/evidence.sqlite3"}
    if (run_dir / "web").is_dir():
        files.update(path.relative_to(run_dir).as_posix() for path in (run_dir / "web").rglob("*") if path.is_file())
    return {
        "review_draft": refs[0],
        "review_index": refs[1],
        "status": report["status"],
        "investigation_workspace": workspace_refs[0],
        "web_ui": workspace_status.get("handle"),
        "terminal": inputs["previous"]["result"]["terminal"],
        "files": [file_record(context, name) for name in sorted(files)],
    }


def verified(context, result):
    from .state import read_seal, read_indexed, verify_files
    terminal = read_seal(context, result["terminal"], "terminal")
    read_indexed(context, terminal["indexed"])
    verify_files(context, [terminal["checkpoint"], terminal["investigation"], *result["files"]])
    return True
