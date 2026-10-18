"""Actionable evidence requests, with ownership supplied only by counsel."""
from mn_temporal_graph_skill import fingerprint


def project(question_id, hypothesis, spans, assignments):
    items = hypothesis.get("work_items", [])
    if not items:
        items = [{"question": q, "requested_record": "Reviewer must specify the record or interview",
                  "why_it_matters": "Resolve the linked factual enquiry", "closure_condition": "Obtain source-backed resolution or record a reviewed limitation",
                  "priority": "Needs review", "priority_basis": "Unresolved enquiry; importance requires reviewer decision",
                  "evidence_ids": hypothesis["supporting_evidence"] + hypothesis["contradictory_evidence"]}
                 for q in hypothesis["outstanding_enquiries"]]
    result = []
    for item in items:
        if not set(item["evidence_ids"]) <= set(spans):
            continue
        gid = "G-" + fingerprint([question_id, item["question"]])[:16]
        assignment = next((r for r in assignments if r["question"] == item["question"]), {})
        result.append({"id": gid, "question": item["question"], "issue_id": question_id,
            "finding_ids": [], "source_evidence_ids": item["evidence_ids"], "origin": "AI suggestion; requires attorney review",
            "requested_record": item["requested_record"], "why_it_matters": item["why_it_matters"],
            "priority": item["priority"], "priority_basis": item["priority_basis"],
            "closure_condition": item["closure_condition"], "status": "Open",
            "owner": assignment.get("owner", "Unassigned"), "internal_target": assignment.get("internal_target"),
            "assignment_basis": "Counsel intake" if assignment else "No attorney assignment supplied"})
    return result
