"""Deterministic reporting, immutable replay and inert evidence previews."""
import html
import json
from pathlib import Path

from mn_sdk.blueprint_support import write_json
from mn_sdk.step_runtime import artifact_reference
from mn_temporal_graph_skill import fingerprint

from .history import history, read, save
from .configuration import investigation_policy


def render_markdown(report):
    text = ["# Mac security investigation", "", f"Knowledge revision: {report['graph_revision']}", "",
            "Local, retrospective evidence review. This report does not establish that the Mac is safe.", ""]
    if report.get("collection_scope") == "macos_unified_logs":
        text += ["This run collected unified-log metadata only. Startup configuration changes and attributed executions are not evaluable.", ""]
    elif not report["cases"]:
        text += ["Evaluation is incomplete; review omitted scope and limits." if report["completeness"]["status"] == "INCOMPLETE_SEARCH"
                 else "No supported startup concerns in the inspected evidence. Review coverage and missing capabilities.", ""]
    for case in report["cases"]:
        text += [f"## {case['title']}", "", f"Case: {case['case_id']} · {case['review_state']}", "",
                 f"Distinct attributed executions: {'at least ' if case.get('execution_count_is_lower_bound') else ''}{case['distinct_execution_count']}.", "",
                 "Malicious intent is not established.", ""]
        if "prior_target" in case:
            # Literal JSON strings keep filenames and embedded Markdown inert in
            # text reports; the HTML preview escapes every source-derived value.
            text += ["```json", json.dumps({"earlier_target": case["prior_target"], "later_target": case["later_target"]}, ensure_ascii=False), "```", ""]
        text += [*case["limitations"], "", f"Evidence references: {len(case['evidence_refs'])}. See evidence.json and the temporal witness.", ""]
    text += ["## Coverage", "", f"Search: {report['completeness']['status']}.", "",
             "Diagnostic logs do not establish startup configuration, execution attribution, actor identity or continuous history.", "",
             "Delivery/installation progression and behavioral baselines are not evaluable in this release.", ""]
    for source in report["coverage"]:
        text.append(f"- {source['availability']} / {source['enumeration']} ({source['revision']}).")
        text += ["```json", json.dumps({k: source.get(k) for k in
                 ("requested_path", "scope", "requested_window", "processes", "capabilities", "gaps")}, ensure_ascii=False), "```", ""]
    return "\n".join(text) + "\n"


def render_html(report, evidence):
    from .timeline import render
    def esc(value):
        return html.escape(str(value), quote=True)
    rows = []
    for case in report["cases"]:
        witness = case["witness"]
        rows.append(f"<section><h2>{esc(case['title'])}</h2><p>{esc(case['review_state'])} · "
                    f"{'At least ' if case.get('execution_count_is_lower_bound') else ''}{case['distinct_execution_count']} distinct attributed executions</p><p>Malicious intent is not established.</p>"
                    f"<details><summary>View temporal witness and graph</summary><pre>{esc(json.dumps(witness, indent=2))}</pre></details>"
                    f"<details><summary>View evidence and acquisition receipts</summary><pre>{esc(json.dumps([evidence[fingerprint(r)] for r in case['evidence_refs']], indent=2))}</pre></details></section>")
    return ("<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
            "<meta http-equiv='Content-Security-Policy' content=\"default-src 'none'; style-src 'unsafe-inline'\">"
            "<title>Mac security investigation</title><style>body{font:15px system-ui;max-width:1000px;margin:30px auto;padding:20px;background:#f5f7f8;color:#172c32}"
            "section{background:white;padding:20px;margin:16px 0;border:1px solid #dbe2e4;border-radius:8px}pre{white-space:pre-wrap;overflow-wrap:anywhere}summary{cursor:pointer;padding:10px 0}</style>"
            f"<h1>Mac security investigation</h1><p>Knowledge revision {report['graph_revision']}. "
            "Retrospective review of inspected evidence; no guarantee that the Mac is safe.</p>"
            + render(report.get("timeline", {"items": []}))
            + ("".join(rows) or ("<p>Unified-log metadata only. Startup configuration changes and attributed executions are not evaluable.</p>"
                                 if report.get("collection_scope") == "macos_unified_logs" else
                                 "<p>Evaluation incomplete. Inspect omitted scope and limits.</p>" if report["completeness"]["status"] == "INCOMPLETE_SEARCH"
                                 else "<p>No supported startup concerns. Inspect coverage before interpreting this result.</p>"))
            + f"<details><summary>Coverage and limitations</summary><pre>{esc(json.dumps(report['coverage'], indent=2))}</pre></details></html>")


def publish_report(context):
    from .timeline import project
    report = read(context, "analysis.json")
    store = history(context)
    root = Path(context["run_dir"])
    try:
        report_id = "assessment-" + fingerprint([report["graph_revision"], report["policy_version"], report["completeness"]["limits"]])
        replay = store.get_report(report_id)
        if replay is not None:
            report = replay
        else:
            if "history_capacity" not in report["completeness"]["unresolved"]:
                report["timeline"] = project(store, report["graph_revision"], investigation_policy()["max_witness_records"])
        previous = store.previous_report(report["graph_revision"])
        old_cases = {c["case_id"]: c for c in (previous or {}).get("cases", [])}
        for case in ([] if replay is not None else report["cases"]):
            material = {k: case.get(k) for k in ("pattern_family", "review_state", "prior_target", "later_target",
                        "distinct_execution_ids", "recurrence", "status", "counterevidence", "unresolved_multiplicity")}
            case["material_digest"] = fingerprint(material)
            old = old_cases.get(case["case_id"])
            changed = old is None or old["material_digest"] != case["material_digest"]
            case["case_revision"] = (old.get("case_revision", 1) if old else 0) + int(changed)
            case["material_change"] = changed
            case["change_reason"] = ("new_concern" if old is None else "assessment_or_behavior_changed"
                                     if changed else "unchanged_reobservation")
        evidence = {}
        for case in report["cases"]:
            for ref in case["evidence_refs"]:
                value = store.resolve_evidence(ref)
                if value["status"] != "retained":
                    raise ValueError("required claim has unavailable source support")
                evidence[fingerprint(ref)] = value
        report["report_id"] = report_id
        # Knowledge revision is fixed; exact replay reads the stored report text,
        # rather than regenerating prose using subsequently acquired evidence.
        report["report_text"] = render_markdown(report)
        binding = fingerprint(report)
        saved = store.get_report(report["report_id"])
        if saved is None:
            store.save_report(report["report_id"], report["graph_revision"], binding, report)
            report = store.get_report(report["report_id"])
        else:
            if fingerprint(saved) != binding:
                raise ValueError("saved report has different semantic inputs")
            report = saved
        refs = [save(context, "final_artifact.json", report), save(context, "evidence.json", evidence)]
        (root / "report.md").write_text(report["report_text"], encoding="utf-8")
        refs.append(artifact_reference("report", "report.md"))
        # Result preview is optional. Failure never blocks the authoritative report.
        try:
            (root / "web").mkdir(exist_ok=True)
            (root / "web/index.html").write_text(render_html(report, evidence), encoding="utf-8")
            refs.append(artifact_reference("preview", "web/index.html"))
        except (OSError, ValueError, TypeError):
            write_json(root / "preview_status.json", {"status": "unavailable"})
        return {"final_artifact": refs[0], "case_count": len(report["cases"]), "report_id": report["report_id"]}, refs
    finally:
        store.close()
