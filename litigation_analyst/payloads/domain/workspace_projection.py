"""A permission-bound investigation snapshot from verified evidence, never cached prose."""
from dataclasses import asdict
import hashlib

from mn_temporal_graph_skill import fingerprint
from .temporal_evidence import project


def build(context, documents, evidence, state, inventory):
    settings = context["config"].get("workspace", {})
    requested = settings.get("authorized_source_ids")
    all_ids = {d.source_id for d in documents}
    if requested is not None and (not isinstance(requested, list) or not set(requested) <= all_ids):
        raise ValueError("workspace.authorized_source_ids must name sources in the frozen matter")
    allowed = all_ids if requested is None else set(requested)
    flagged = set(state["data"].get("source_review_flags", {}))
    # A mailbox original may contain excluded records. Never expose the container
    # when even one member is restricted, including potential privileged material.
    forbidden_containers = {d.container_source_id for d in documents
        if d.source_id not in allowed or d.source_id in flagged}
    documents = [d for d in documents if d.source_id in allowed and d.source_id not in flagged]
    by_source = {d.source_id: d for d in documents}
    spans = {}
    for e in evidence:
        source = by_source.get(e.source_id)
        if source is None:
            continue
        if (source.text is None or hashlib.sha256(source.text.encode()).hexdigest() != e.content_sha256
                or not 0 <= e.start_offset < e.end_offset <= len(source.text)
                or source.text[e.start_offset:e.end_offset] != e.text):
            raise ValueError("Workspace citation unavailable: exact source binding failed")
        spans[e.evidence_id] = asdict(e)
    originals = {r["path"]: r for r in inventory["files"]}
    sources = []
    for d in documents:
        path = d.container_source_id.removeprefix("case:") if d.container_source_id else d.relative_path
        original = originals[path]
        sources.append({**asdict(d), "original_sha256": original["sha256"],
            "original_included": d.container_source_id not in forbidden_containers,
            "extraction_status": "Readable normalized text; completeness not certified" if d.text is not None else "Unreadable; not searched",
            "locator_basis": "Generated normalized character offsets; official page/line identifiers are not inferred",
            "review_state": "Awaiting review"})
    temporal = project(tuple(documents), inventory["repository_id"])
    # Headers from the deterministic temporal adapter are source-backed citations.
    for event in temporal["events"]:
        for ref in event["evidence_refs"]:
            spans.setdefault(ref["evidence_id"], {**ref, "provenance_kind": "observed"})
    hypotheses, gaps, findings = [], {}, []
    raw_hypotheses = state["data"].get("hypotheses", {})
    accepted = set(state["data"].get("report_review", {}).get("accepted_ids", []))
    for h in raw_hypotheses.values():
        ids = h["supporting_evidence"] + h["contradictory_evidence"]
        # Do not publish a conclusion whose basis depends on inaccessible evidence.
        if not set(ids) <= set(spans):
            continue
        question_id = "Q-" + fingerprint(h["question"].casefold())[:16]
        item = {**h, "id": question_id, "origin": "Model enquiry", "mode": "Investigation question",
            "definition": "Factual enquiry; no counsel-defined legal test supplied", "gap_ids": []}
        for question in h["outstanding_enquiries"]:
            gid = "G-" + fingerprint([question_id, question])[:16]
            item["gap_ids"].append(gid)
            gaps[gid] = {"id": gid, "question": question, "issue_id": question_id,
                "finding_ids": [], "source_evidence_ids": ids, "origin": "AI suggestion",
                "priority_basis": "Unresolved enquiry; importance requires reviewer decision",
                "closure_condition": "Obtain source-backed resolution or record a reviewed limitation",
                "status": "Open", "owner": "Unassigned", "internal_target": None}
        hypotheses.append(item)
    by_hypothesis = {h["question"]: h for h in hypotheses}
    for f in state["data"].get("report_draft", {}).get("findings", []):
        if f["id"] not in accepted or not set(f["evidence_ids"]) <= set(spans):
            continue
        linked = [h for h in raw_hypotheses.values() if set(f["evidence_ids"]) &
                  set(h["supporting_evidence"] + h["contradictory_evidence"])]
        # Preserve the full known counter-basis even when it wasn't in the short finding.
        required = {i for h in linked for i in h["supporting_evidence"] + h["contradictory_evidence"]}
        if not required <= set(spans):
            continue
        questions = [by_hypothesis[h["question"]] for h in linked if h["question"] in by_hypothesis]
        support = list(dict.fromkeys(f["evidence_ids"] + [i for h in linked for i in h["supporting_evidence"]]))
        counter = list(dict.fromkeys(i for h in linked for i in h["contradictory_evidence"]))
        stable = "F-" + fingerprint([context["payload"]["goal"],
            sorted(h["question"] for h in linked) or [f["id"]], f["section"]])[:16]
        gap_ids = list(dict.fromkeys(i for h in questions for i in h["gap_ids"]))
        material = {"title": f["title"], "assessment": f["assessment"], "limitations": f["limitations"],
            "support": [{k: spans[i][k] for k in ("source_id", "content_sha256", "start_offset", "end_offset")} for i in support],
            "counter": [{k: spans[i][k] for k in ("source_id", "content_sha256", "start_offset", "end_offset")} for i in counter],
            "alternatives": [a for h in linked for a in h["alternatives"]], "gaps": [gaps[i]["question"] for i in gap_ids]}
        findings.append({**f, "id": stable, "model_finding_id": f["id"], "material_digest": fingerprint(material),
            "origin": "Model assessment", "source_basis": "Inferred assessment of cited source statements",
            "model_review": "Evidence-grounding check completed; not attorney review", "review_state": "AI draft",
            "evidentiary_assessment": "Contested" if counter else "Unresolved",
            "supporting_evidence": support, "counter_evidence": counter,
            "alternatives": material["alternatives"], "issue_ids": [h["id"] for h in questions], "gap_ids": gap_ids,
            "revision": 1, "review_history": []})
        for gid in gap_ids:
            gaps[gid]["finding_ids"].append(stable)
    visible_ids = set(by_source)
    # Keep source/path locators out of overview metadata and never reveal excluded counts.
    snapshot = fingerprint({"sources": [(d.source_id, d.content_sha256) for d in documents],
                            "findings": [f["material_digest"] for f in findings]})
    return {"version": "mn.litigation.workspace.v1", "snapshot_id": snapshot,
        "matter_id": inventory["repository_id"], "title": settings.get("matter_name", "Litigation investigation"),
        "goal": context["payload"]["goal"], "access_scope": context["config"]["investigation"]["access_scope"],
        "audience": "Authorized local matter owner", "sample": bool(inventory.get("sample")),
        "sources": sources, "evidence": list(spans.values()), "findings": findings,
        "issues": hypotheses, "gaps": list(gaps.values()), "temporal": temporal,
        "analysis": {"stop_reason": state["stop_reason"], "status": "Incomplete analysis" if
            state["stop_reason"] in {"cancelled", "investigation_deadline_reached", "iteration_limit_exhausted",
                "tool_call_budget_exhausted", "maximum_rounds_reached"} else "Draft for human review",
            "scope": "Authorized frozen sources; ranked retrieval is not exhaustive"},
        "coverage": {"source_ids": sorted(visible_ids), "readable_ids": [d.source_id for d in documents if d.text is not None],
            "unreadable_ids": [d.source_id for d in documents if d.text is None],
            "definition": "Authorized source records with readable normalized text; not proof of complete extraction or review"},
        "privacy": {"case_data_network_requests": "Workspace makes no network requests",
            "model_location": "Configured runtime model; deployment location is not attested by this output",
            "access": "Local file copy; no authenticated multi-user sharing service",
            "export": "Copies cannot be revoked; recipient authorization must be confirmed"},
        "capabilities": {"financial_scenarios": "Unavailable: reviewed source inputs and methodology not supplied",
            "legal_elements": "Unavailable: counsel-defined framework not supplied",
            "case_qa": "Use the co-worker chat for Membrane-backed questions; webpage search is a literal record filter",
            "identity_corrections": "Person identity is unresolved; address nodes are never silently merged"}}
