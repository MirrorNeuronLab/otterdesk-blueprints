"""Render architecture review evidence and inferred recommendations."""
import json
from .prompts import anchor

def render_markdown(report):
    if "decisions" in report:
        from .adaptive_report import render_adaptive_report
        return render_adaptive_report(report)
    lines = ["# Architecture investigation", "", f"Goal: {report['goal']}", "",
             f"Status: **{report['status']}** · {report['mode']}", f"Snapshot: `{report['snapshot']}`", "",
             "This is a review draft. Query observations are separated from inferred recommendations. Citation validity does not automatically establish that a narrative inference follows from its sources.",
             "", "[Suggested Codex tasks](suggestive_prompts.md) · [Knowledge selection audit](knowledge.json) · [Timestamped actions](events.log)",
             "", "## Evidence coverage", "", "```json", json.dumps(report["coverage"], indent=2), "```"]
    # Lead with reviewable actions; retain all evidence and audit below.
    brief = ["", "## Decision brief", ""]
    if report.get("decision"):
        decision = report["decision"]
        if decision.get("finding_id"):
            brief.extend([f"[Open the Codex task for this decision](suggestive_prompts.md#{anchor(decision['finding_id'])})", ""])
        brief.extend([f"**Focus:** {decision['focus']} · {decision['verdict']}", "",
                      f"**Recommendation:** {decision['recommendation']}", "",
                      f"**Next action:** {decision['next_action']}", "",
                      f"**Acceptance criterion:** {decision['acceptance_test']}", "",
                      f"**Rollback:** {decision['rollback']}", "",
                      decision.get("policy", "Model-inferred final advice; human review required."), "",
                      decision["interpretation"]["text"] + " [" + ", ".join(decision["interpretation"]["evidence_ids"]) + "]", ""])
        for label, field in (("Tradeoffs", "tradeoffs"), ("Alternatives", "alternatives"), ("Missing evidence", "missing_evidence")):
            brief.extend([f"**{label}:**", "", *["- " + t for t in decision[field]], ""])
        brief.extend(["**Counter-evidence:**", ""])
        for claim in decision["counter_evidence"]:
            brief.append("- " + claim["text"] + " [" + ", ".join(claim["evidence_ids"]) + "]")
        brief.extend(["", "The final review covers the lead candidate. Other findings below are exploratory assessments, not independently reviewed recommendations.", ""])
    for finding in report["findings"]:
        if finding["status"] == "assessed" and not report.get("decision"):
            a = finding["assessment"]
            brief.extend([f"- **{finding['id']} · {finding['hypothesis']['module']} · {a['verdict']}**: {a['recommendation']}",
                          f"  Next: {a['next_action']}"])
    if not any(f["status"] == "assessed" for f in report["findings"]):
        brief.append("No validated model assessment is available. Inspect the recorded errors before using this report.")
    brief.extend(["", "Order reflects the goal-directed investigation plan, not measured business value or refactoring ROI."])
    coverage_index = lines.index("## Evidence coverage")
    lines[coverage_index:coverage_index] = brief + [""]
    for warning in report["warnings"]:
        lines.extend(["", f"Coverage warning: {warning}"])
    for finding in report["findings"]:
        h = finding["hypothesis"]
        lines.extend(["", f'<a id="finding-{finding["id"].lower()}"></a>', "",
                      f"## {finding['id']} · {h['module']}", "", f"**Hypothesis:** {h['statement']}", "",
                      f"[Copy the Codex task](suggestive_prompts.md#{anchor(finding['id'])})"])
        if finding.get("knowledge_ids"):
            links = [f"[{kid}](#practice-{kid.lower()})" for kid in finding["knowledge_ids"]]
            lines.extend(["", "**Review guidance (not evidence):** " + ", ".join(links)])
        if finding["status"] != "assessed":
            lines.extend(["", f"Assessment failed: {finding.get('error', finding['status'])}"])
            continue
        a = finding["assessment"]
        lines.extend(["", f"**Recommendation (inferred):** {a['recommendation']}", "",
                      f"**Verdict:** {a['verdict']} · {finding['confidence']}", "", "### Executed evidence", ""])
        for qid in finding["query_ids"]:
            q = next(q for q in report["queries"] if q["id"] == qid)
            observation = q["rows"] if q["status"] == "ok" else {"status": q["status"], "error": q.get("error", "Required evidence unavailable")}
            lines.extend([f"**{qid} · {q['tool']}** — {q.get('limit_note', 'No conclusion: required evidence unavailable')}", "", "```json", json.dumps(observation, indent=2), "```", ""])
        lines.extend(["### Interpretation", "", a["interpretation"]["text"] + " [" + ", ".join(a["interpretation"]["evidence_ids"]) + "]",
                      "", "### Counter-evidence", ""])
        for claim in a["counter_evidence"]:
            lines.append("- " + claim["text"] + " [" + ", ".join(claim["evidence_ids"]) + "]")
        if not a["counter_evidence"]:
            lines.append("No disconfirming interpretation established. The counter-search was executed; absence from its top results is not evidence of absence.")
        for label, field in (("Next action", "next_action"), ("Acceptance criterion (proposed)", "acceptance_test"), ("Rollback", "rollback")):
            lines.extend(["", f"**{label}:** {a[field]}"])
        for label, field in (("Tradeoffs (possible costs, not observed counter-evidence)", "tradeoffs"), ("Alternatives", "alternatives"), ("Missing evidence", "missing_evidence")):
            lines.extend(["", f"### {label}", "", *["- " + item for item in a[field]]])
    knowledge = report.get("knowledge", {})
    if knowledge.get("enabled"):
        lines.extend(["", "## Architecture review knowledge", "",
                      f"Library version: `{knowledge['version']}` · SHA-256: `{knowledge['sha256']}`", "",
                      "These are retrieved review methods, not evidence of a defect. The selection audit records cards supplied to model requests; offline runs only retrieve guidance for the reviewer and Codex tasks.", ""])
        for kid, card in knowledge["cards"].items():
            lines.extend([f'<a id="practice-{kid.lower()}"></a>', "", f"### {kid} · {card['title']}", "",
                          card["principle"], "", f"**Verify:** {card['verify']}", "",
                          f"**Counter-check:** {card['exception']}", "", f"Origin: {card['origin']}.", ""])
            for source in card["sources"]:
                lines.extend([f"Source: [{source['title']}]({source['url']}).", ""])
    lines.extend(["", "## Query audit", ""])
    for q in report["queries"]:
        params = {k: (f"{len(v)}-dimension vector stored in report.json" if k == "query_vec" else v) for k, v in q["params"].items()}
        lines.extend([f"### {q['id']} · {q['status']}", "", "```cypher", q["query"], "```", "",
                      "Parameters: `" + json.dumps(params) + "`", "",
                      f"Result SHA-256: `{q.get('result_sha256', 'unavailable')}` · {q['elapsed_ms']} ms", ""])
    lines.extend(["## Source evidence", ""])
    for eid, ev in report["evidence"].items():
        lines.extend([f"### {eid}", "", f"`{ev['path']}:{ev['line_start']}-{ev['line_end']}` · {ev['kind']}",
                      f"SHA-256: `{ev['sha256']}`", "", "```text", ev["text"].replace("```", "` ` `"), "```", ""])
    if report["errors"]:
        lines.extend(["## Errors", "", *["- " + error for error in report["errors"]]])
    lines.extend(["", "## Measurements", "", "```json", json.dumps(report["metrics"], indent=2), "```", ""])
    return "\n".join(lines)
