"""Actionable evidence requests, with ownership supplied only by counsel."""
from mn_temporal_graph_skill import fingerprint
import re


def classify(gap, documents):
    """Route exact inventory matches to reread; never claim a missing record exists."""
    request = gap['requested_record'].casefold()
    if re.search(r'privileg|legal advice|attorney.client|work product', request):
        return {**gap, 'question':'Handling review: ' + gap['question'],
            'requested_record':'Handling decision only: ' + gap['requested_record'],
            'priority_basis':'Counsel must decide handling before any substantive use. ' + gap.get('priority_basis', ''),
            'status':'Handling review', 'work_type':'handling_review',
            'routing_reason':'Counsel must decide handling; restricted records are not a collection request.'}
    # These named record classes identify existing documents, not whether an
    # approval authorizes a different amount or a ledger proves bank settlement.
    classes = {'ledger':r'ledger|accounting entries', 'policy':r'policy|policies'}
    matches = [d.source_id for d in documents if d.text and any(
        re.search(pattern, request) and re.search(pattern, d.relative_path + ' ' + d.text.splitlines()[0], re.I)
        for pattern in classes.values())]
    if matches:
        return {**gap, 'question':'Internal reread: ' + gap['question'],
            'requested_record':'Already available for internal reread: ' + gap['requested_record'],
            'priority_basis':'Matching records are already available; re-read before collection. ' + gap.get('priority_basis', ''),
            'status':'Internal reread', 'work_type':'internal_reread',
            'available_source_ids':sorted(matches),
            'routing_reason':'Matching records are already in the cleared inventory. Re-read them before asking for additional records.'}
    return {**gap, 'work_type':'customer_follow_up',
        'routing_reason':'No matching record established by this inventory check; confirm with counsel.'}


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
