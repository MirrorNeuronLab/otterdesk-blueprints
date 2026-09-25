"""A decision-oriented report with a traceable, independently reviewed roadmap."""
import json

from .prompts import anchor, fence


def cite(ids):
    return " ".join(f"[{eid}](#evidence-{eid.lower()})" for eid in ids)


def claim(value):
    return value["text"] + " " + cite(value["evidence_ids"])


def render_adaptive_report(report):
    reviewed = [f for f in report["findings"] if f.get("review_status") == "reviewed"]
    changes = [f for f in reviewed if f["review"]["action_kind"] == "change"]
    verification = [f for f in reviewed if f["review"]["action_kind"] == "verify"]
    lines = ["# Software architecture review", "", f"**Objective:** {report['goal']}", "",
        f"**Status:** {report['status']} · {report['mode']}", f"**Source snapshot:** `{report['snapshot']}`", "",
        "## Executive summary", "",
        f"Hypotheses investigated: {len(report['findings'])}. Independently reviewed: {len(reviewed)}. Candidate changes: {len(changes)}. Verification tasks: {len(verification)}.", "",
        f"**Investigation stopped because:** {report['stop_reason']}.", ""]
    if reviewed:
        lead = reviewed[0]["review"]
        lines += [f"**First priority — {reviewed[0]['hypothesis']['module']}:** {lead['next_action']}", "", claim(lead["interpretation"]), ""]
    else:
        lines += ["No independently reviewed change is ready for the implementation roadmap. The findings below identify evidence and questions for further validation.", ""]
    if report["status"] == "partial":
        lines += ["**Incomplete investigation:** the stated stopping limit or missing evidence prevented a complete investigation. Unreviewed proposals are excluded from the implementation roadmap.", ""]
    lines += ["## Architecture overview", "",
        "The following relationships are observations from the captured static or supplied graph. They do not establish runtime call order, operational guarantees, or business ownership.", ""]
    seen = set()
    for q in report["queries"]:
        if q["tool"] in {"dependencies", "calls"}:
            for row in q["rows"]:
                pair = (row.get("source"), row.get("target"))
                if all(pair) and pair not in seen:
                    seen.add(pair)
                    relation = "depends on" if q["tool"] == "dependencies" else "has a statically identified call candidate to"
                    lines.append(f"- `{pair[0]}` {relation} `{pair[1]}`. " + cite([q["id"]]))
    if not seen:
        lines.append("No dependency relationships were established by the executed queries; the architecture overview is incomplete.")
    structural = report.get("structural_analysis")
    if structural:
        lines += ["", "## Structural dependency baseline", "",
                  f"The frozen source graph contains {structural['module_count']} indexed modules and {structural['dependency_edges']} direct dependency pairs.", "",
                  f"Static strongly connected cycles: {len(structural['cycles'])}. The [evidence-linked dependency data]({structural['path']}) records exact source locations.", ""]
        if structural["dsm"]["status"] == "ready":
            lines += [f"[Download the dependency DSM]({structural['dsm']['path']}). Rows import columns; 1 means a direct dependency.", ""]
        else:
            lines += [f"The dense DSM was omitted because the module count exceeds the {structural['dsm']['max_modules']}-module size limit. The JSON dependency list remains complete.", ""]
        if structural["cycles"]:
            lines += ["Cycles (static source relationships, not demonstrated failures):", ""]
            lines += ["- " + " → ".join(group) for group in structural["cycles"][:10]]
            lines += [""]
        if structural["bridge_modules"]:
            lines += ["Bridge modules in the undirected dependency projection: " + ", ".join(f"`{name}`" for name in structural["bridge_modules"][:10]) + ".", ""]
        lines += ["Degree and cycles are investigation signals, not severity, measured change impact, or production incidents.", ""]
    lines += ["", "## Prioritized findings", "", report["priority_method"], ""]
    for index, f in enumerate(report["findings"], 1):
        h = f["hypothesis"]
        lines += [f"### {index}. {f['id']} — {h['module']}", "", f"**Question:** {h['statement']}", "",
            f"**Latest hypothesis revision:** {f['revision']}", ""]
        if f.get("retirement"):
            r = f["retirement"]
            lines += ["**Retired hypothesis:** " + r["reason"] + " " + cite(r["evidence_ids"]), ""]
            continue
        a = f.get("review", f.get("assessment"))
        if not a:
            lines += [f"**Incomplete:** {f.get('error', 'No validated assessment was produced.')}", ""]
            continue
        basis = "Independently reviewed" if f.get("review") else "Exploratory; excluded from the implementation roadmap"
        lines += [f"**Verdict:** {a['verdict']} · {basis}", "", f"**Confidence limits:** {f['confidence']}", "",
            "**Architectural consequence / interpretation:** " + claim(a["interpretation"]), "",
            "**Supporting observations:** " + cite(f["query_ids"]), "", "**Counter-evidence:**", ""]
        lines += ["- " + claim(c) for c in a["counter_evidence"]] or ["No disconfirming interpretation was established. Search absence does not prove absence of counter-evidence."]
        for title, key in (("Recommendation", "recommendation"), ("Next action", "next_action"), ("Acceptance check", "acceptance_test"), ("Rollback", "rollback")):
            lines += ["", f"**{title}:** {a[key]}"]
        for title, key in (("Alternatives and when to prefer them", "alternatives"), ("Tradeoffs", "tradeoffs"), ("Decisive unknowns", "missing_evidence")):
            lines += ["", f"**{title}:**", ""] + ["- " + item for item in a[key]]
        lines += ["", f"[Evidence-scoped coding task](suggestive_prompts.md#{anchor(f['id'])})", ""]
    lines += ["## Phased implementation roadmap", "",
        "Only independently reviewed advice appears here. Validate the current revision and cited constraints before implementing any proposed change.", ""]
    for title, kinds in (("Phase 1 — resolve uncertainty", {"verify"}), ("Phase 2 — make bounded changes", {"change"}), ("Phase 3 — preserve and monitor justified constraints", {"preserve"})):
        selected = [f for f in reviewed if f["review"]["action_kind"] in kinds]
        lines += [f"### {title}", ""]
        if not selected:
            lines += ["No independently reviewed task in this phase.", ""]
        for f in selected:
            a = f["review"]
            lines += [f"- **{f['id']} · {f['hypothesis']['module']}:** {a['next_action']}",
                      f"  Acceptance: {a['acceptance_test']}", f"  Rollback: {a['rollback']}", ""]
    lines += ["## Coverage and limitations", "", f"Stop reason: {report['stop_reason']}", "",
        ("Static imports are not runtime calls. Similarity and top-k search results do not establish completeness. "
        "Source citations ground observations; recommendations remain reviewable inferences. Repository code and tests were not executed."), "",
        *["- " + warning for warning in report["warnings"]], "", fence(json.dumps(report["coverage"], indent=2)), "",
        "[Plan history](investigation-plan.json) · [Full structured report](report.json) · [Model audit](model-trace.json)", "",
        "## Evidence appendix", ""]
    for q in report["queries"]:
        lines += [f'<a id="evidence-{q["id"].lower()}"></a>', "", f"### {q['id']} — {q['tool']}", "",
            f"Status: {q['status']}. {q.get('limit_note', 'Bounded result; absence is not proof of absence.')}", "",
            fence(json.dumps(q["rows"], indent=2)), "", f"Result hash: `{q.get('result_sha256', 'unavailable')}`", ""]
    for eid, ev in report["evidence"].items():
        lines += [f'<a id="evidence-{eid.lower()}"></a>', "", f"### {eid}", "",
            f"`{ev['path']}:{ev['line_start']}-{ev['line_end']}` · {ev['kind']}", f"SHA-256: `{ev['sha256']}`", "", fence(ev["text"]), ""]
    lines += ["## Run accounting", "", fence(json.dumps(report["metrics"], indent=2)), ""]
    return "\n".join(lines)
