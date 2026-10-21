"""Sealed domain assessments projected as data for stock report publication."""
import json

from mn_sdk.agent_events import report_activity
from mn_sdk_common.reports import ReportDocument
from mn_temporal_graph_skill import fingerprint

from .configuration import BLUEPRINT_ID, investigation_policy
from .history import history
from .timeline import project as project_timeline


def document(report):
    """Keep uncertainty and exact support in presentation data, without rendering."""
    qualification = ("This run collected unified-log metadata only. Startup configuration changes and attributed executions are not evaluable."
        if report.get("collection_scope") == "macos_unified_logs" else
        "Evaluation is incomplete; review omitted scope and limits."
        if report["completeness"]["status"] == "INCOMPLETE_SEARCH" else
        "No supported startup concerns in the inspected evidence. Review coverage and missing capabilities."
        if not report["cases"] else "Supported temporal patterns require human review; malicious intent is not established.")
    cases = []
    for case in report["cases"]:
        details = {key: case[key] for key in ("case_id", "review_state", "distinct_execution_count", "limitations", "witness")}
        details.update({key: case[key] for key in ("prior_target", "later_target", "execution_count_is_lower_bound") if key in case})
        cases.append({"text": case["title"] + "\n" + json.dumps(details, ensure_ascii=False, sort_keys=True),
            "source_refs": ["evidence.json#" + fingerprint(ref) for ref in case["evidence_refs"]]})
    timeline = report.get("timeline", {"items": []})
    rows = [[item["lane"], item["label"], item["kind"], item["time"].get("earliest") or "Unknown",
             item["time"].get("latest") or "Unknown", item["known_from_revision"]] for item in timeline["items"]]
    return {"schema_version": "mn.report_document.v1", "title": "Mac security investigation",
        "identity": f"Knowledge revision: {report['graph_revision']}",
        "summary": "Local, retrospective evidence review. This report does not establish that the Mac is safe.",
        "sections": [
            {"id": "findings", "title": "Evidence-backed observations", "blocks": [
                {"type": "warning", "text": qualification},
                {"type": "warning", "text": "Malicious intent is not established."},
                {"type": "findings", "items": cases}]},
            {"id": "timeline", "title": "Evidence timeline", "blocks": [
                {"type": "table", "columns": ["Scope", "Record", "Kind", "Earliest UTC", "Latest UTC", "First known revision"], "rows": rows,
                 "caption": timeline.get("qualification", "Timeline bounds are unknown.")},
                {"type": "paragraph", "text": "State/event time and scan acquisition are separate. Unobserved intervals remain unknown."}]},
            {"id": "coverage", "title": "Coverage and limitations", "blocks": [
                {"type": "metric", "label": "Search", "value": report["completeness"]["status"]},
                {"type": "warning", "text": "Diagnostic logs do not establish startup configuration, execution attribution, actor identity or continuous history. Delivery/installation progression and behavioral baselines are not evaluable in this release."},
                {"type": "paragraph", "text": json.dumps(report["coverage"], ensure_ascii=False, sort_keys=True)},
                {"type": "attachments", "items": [{"label": "Retained evidence and acquisition receipts", "path": "evidence.json"},
                    {"label": "Sealed assessment", "path": "final_artifact.json"}]}]}]}


def project(block, inputs):
    report_activity("Projecting the security evidence report", owner_blueprint=BLUEPRINT_ID, step_id=block.step_id, run_dir=block.store.run_dir)
    report = block.store.read(inputs["previous"]["analysis"])
    ledger = history(block, report["host_epoch_id"])
    try:
        report_id = "assessment-v3-" + fingerprint([report["graph_revision"], report["policy_version"], report["completeness"]["limits"]])
        replay = ledger.get_report(report_id)
        if replay is not None:
            report = replay
        else:
            if "history_capacity" not in report["completeness"]["unresolved"]:
                report["timeline"] = project_timeline(ledger, report["graph_revision"], investigation_policy()["max_witness_records"])
            previous = ledger.previous_report(report["graph_revision"])
            old_cases = {case["case_id"]: case for case in (previous or {}).get("cases", [])}
            for case in report["cases"]:
                material = {key: case.get(key) for key in ("pattern_family", "review_state", "prior_target", "later_target",
                    "distinct_execution_ids", "recurrence", "status", "counterevidence", "unresolved_multiplicity")}
                case["material_digest"] = fingerprint(material)
                old = old_cases.get(case["case_id"])
                changed = old is None or old["material_digest"] != case["material_digest"]
                case["case_revision"] = (old.get("case_revision", 1) if old else 0) + int(changed)
                case["material_change"] = changed
                case["change_reason"] = "new_concern" if old is None else "assessment_or_behavior_changed" if changed else "unchanged_reobservation"
        evidence = {}
        for case in report["cases"]:
            for ref in case["evidence_refs"]:
                retained = ledger.resolve_evidence(ref)
                if retained["status"] != "retained":
                    raise ValueError("required claim has unavailable source support")
                evidence[fingerprint(ref)] = retained
        if replay is None:
            report["report_id"] = report_id
            report["report_document"] = ReportDocument.from_dict(document(report)).to_dict()
            ledger.save_report(report_id, report["graph_revision"], fingerprint(report), report)
            report = ledger.get_report(report_id)
        published = {**report, "output_files": [
            {"kind": "final_artifact", "path": "final_artifact.json"},
            {"kind": "evidence", "path": "evidence.json"}, {"kind": "report", "path": "report.md"}]}
        return {"document": report["report_document"], "data": {"final_artifact": published, "evidence": evidence}}
    finally:
        ledger.close()
