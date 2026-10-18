"""Attorney-facing issue coverage and independently cited arithmetic exhibits."""
import html

from mn_temporal_graph_skill import fingerprint

from .financial_review import build as reconcile


def attach(workspace, context, matter, documents, spans, plan):
    visible = {d.source_id for d in documents}
    financial = reconcile({**matter, "financial_events": [r for r in matter["financial_events"] if r["source_id"] in visible]}, documents, {})
    for row in financial["evidence"]:
        spans.setdefault(row["evidence_id"], row)
    workspace["evidence"] = list(spans.values())
    workspace["financial_review"] = financial
    workspace["matter_scope"] = {k: matter[k] for k in ("intended_decision", "parties", "transaction_refs")}
    rows = []
    for issue in matter["issues"]:
        linked = [h for h in workspace["issues"] if issue["id"] in h.get("counsel_issue_ids", [])]
        rows.append({**issue, "status": "Examined through AI hypotheses; requires attorney review" if linked else "Unexamined in this review",
            "framework_basis": "Counsel-supplied review direction, not verified applicable law or case evidence",
            "hypothesis_ids": [h["id"] for h in linked],
            "supporting_evidence": list(dict.fromkeys(i for h in linked for i in h["supporting_evidence"])),
            "counter_evidence": list(dict.fromkeys(i for h in linked for i in h["contradictory_evidence"])),
            "unknowns": list(dict.fromkeys(q for h in linked for q in h["outstanding_enquiries"])),
            "gap_ids": list(dict.fromkeys(i for h in linked for i in h["gap_ids"]))})
    workspace["counsel_issues"] = rows
    for finding in workspace["findings"]:
        related = [row for row in rows if set(row["hypothesis_ids"]) & set(finding["issue_ids"])]
        finding["counsel_issue_ids"] = [row["id"] for row in related]
        finding["material_digest"] = fingerprint([finding["material_digest"], workspace["matter_scope"],
            [{k: row.get(k) for k in ("id", "question", "legal_framework")} for row in related]])
    workspace["analysis"]["review_plan"] = plan
    workspace["analysis"]["unexamined_issue_ids"] = [r["id"] for r in rows if not r["hypothesis_ids"]]
    workspace["analysis"]["partial_review"] = plan["profile"] == "first_pass" or bool(workspace["analysis"]["unexamined_issue_ids"]) or workspace["analysis"]["status"] == "Incomplete analysis"
    if workspace["analysis"]["partial_review"]:
        workspace["analysis"]["status"] = "Partial review — draft for attorney review"
    workspace["capabilities"]["financial_scenarios"] = financial["status"] + "; arithmetic only, no damages or settlement determination"
    workspace["capabilities"]["legal_elements"] = "Counsel-provided issues/framework; legal applicability remains unverified" if rows else "Unavailable: counsel-defined framework not supplied"
    workspace["snapshot_id"] = fingerprint([workspace["snapshot_id"], workspace["matter_scope"], rows, financial, plan])
    return workspace


def escaped(value):
    value = html.escape(str(value))
    for char in "[]()*_`":
        value = value.replace(char, "\\" + char)
    return value


def transaction_appendix(financial):
    lines = ["# Transaction reconciliation", "", financial["status"], "",
        "Event classifications, ledger grouping and any supplied dates are counsel annotations. Exact quotations and recorded numbers are verified; legal effect and external settlement are not.", ""]
    for transaction in financial["transactions"]:
        lines += ["## " + escaped(transaction["transaction_ref"]) + " · " + escaped(transaction["currency"]), "",
            "Ledger group (counsel annotation): " + escaped(transaction["ledger_id"]), "",
            "Posting / reversal net: " + escaped(transaction["posting_reversal_net"]),
            "Recorded net values: " + escaped(", ".join(transaction["recorded_net_values"])),
            "Request minus stated approval: " + escaped(transaction["request_minus_approval"]), "",
            transaction["qualification"], ""]
    for evidence in financial["evidence"]:
        lines += [f'<a id="evidence-{evidence["evidence_id"]}"></a>',
            "### Exact transaction passage " + evidence["evidence_id"], "",
            escaped(evidence["source_id"]) + " · normalized SHA-256 " + evidence["content_sha256"] +
            f" · generated character span {evidence['start_offset']}:{evidence['end_offset']}", "",
            *["> " + html.escape(line) for line in evidence["text"].splitlines()], ""]
    return "\n".join(lines)


def report_sections(workspace):
    lines = ["## Counsel issue coverage", "", "Counsel scope is review direction, not a legal conclusion or source evidence.", ""]
    for issue in workspace["counsel_issues"]:
        lines += ["### " + escaped(issue["id"]) + ": " + escaped(issue["question"]), "", escaped(issue["status"]), "",
            "Supporting passage IDs: " + ", ".join(issue["supporting_evidence"]),
            "Counterevidence passage IDs: " + ", ".join(issue["counter_evidence"]),
            "Unresolved: " + escaped("; ".join(issue["unknowns"]) or "No answer is established by the absence of an item."), ""]
    if not workspace["counsel_issues"]:
        lines += ["No counsel-defined questions supplied; the model's factual enquiries are not a substitute for a legal framework.", ""]
    plan = workspace["analysis"]["review_plan"]
    lines += ["## Review allowance and unexamined scope", "",
        f"Profile: {plan['profile']}. Up to {plan['max_rounds']} round(s), {plan['max_decisions']} investigation decisions, plus one separate readiness decision and {plan['relationship_call_ceiling']} separate relationship-extraction decisions.",
        f"Planning-boundary time allowance: {plan['seconds']} seconds; an in-flight request can extend elapsed time.",
        plan["definition"], "This is not a billing forecast, completeness certificate or confirmation that every source was reviewed.", "",
        "## Next evidence work", ""]
    for gap in workspace["gaps"]:
        lines += ["### " + escaped(gap["question"]), "",
            "Record or interview requested: " + escaped(gap["requested_record"]),
            "Decision it informs: " + escaped(gap["why_it_matters"]),
            "Closure test: " + escaped(gap["closure_condition"]),
            "Proposed priority: " + escaped(gap["priority"]) + " — " + escaped(gap["priority_basis"]),
            "Owner: " + escaped(gap["owner"]) + " · internal target: " + escaped(gap["internal_target"] or "Not assigned"),
            "Basis passage IDs: " + ", ".join(gap["source_evidence_ids"]),
            "Draft for attorney review; no communication or collection was performed.", ""]
    lines += ["## Transaction review", "", "See [source-bound transaction reconciliation](transaction_appendix.md). Accounting arithmetic is not a finding about bank settlement, loss, intent or liability.", ""]
    return "\n".join(lines)
