"""Independent review and deterministic synthesis of prioritized architecture advice."""
from .evidence_tasks import packet_for, validate_advice, verification_policy
from .investigation_store import BudgetExhausted, RecordedModel
from .investigator import ASSESS, validated_completion
from .knowledge import KnowledgeBase, evidence_room


def finalize_investigation(store, reason, *, incomplete, llm_client=None):
    snapshot = store.read("snapshot.json")
    findings = store.findings()
    decisions = []
    knowledge = KnowledgeBase(store.config).audit
    for finding in findings:
        if finding.get("retirement"):
            finding["review_status"] = "retired"
            continue
        if finding["status"] != "assessed":
            incomplete = True
            continue
        prior = finding["assessment"]
        if store.config["offline"]:
            finding["review_status"] = "offline_unreviewed"
            continue
        instruction = ASSESS + "\nIndependently review this candidate, including its counter-evidence. Prior advice is unverified. Re-check technical correctness, especially transaction participants and external effects. Moving a network call inside a database transaction does not make it atomic or reversible. Do not prescribe distributed transactions without an evidenced need and participant support. Distinguish a demonstrated static risk from an observed production incident. Explicitly weigh visible intentional orchestration and existing local atomicity as counter-evidence. If missing_evidence has decisive gaps, action_kind must be verify or preserve; recommend targeted experiments before changes. Return action_kind verify, preserve or change. Inconclusive advice must be a project-specific verification task. Its rollback removes only newly added instrumentation or harnesses; never revert existing repository changes."
        if finding["unavailable_evidence"]:
            instruction += "\nRequired views or architecture rules are unavailable; verdict must be inconclusive."
        data = {"review_policy": True, "goal": store.context["payload"]["goal"], "hypothesis": finding["hypothesis"],
                "prior_proposal": prior, "packet": {}, "unavailable_evidence": finding["unavailable_evidence"]}
        records = [r for r in store.results() if r["hypothesis_id"] == finding["id"] and r["revision"] == finding["revision"]]
        packet = packet_for(records, min(9000, evidence_room(store.config, instruction, data)))
        data["packet"] = packet
        try:
            model = RecordedModel(store, f"review-{finding['id']}-r{finding['revision']}", llm_client, final=True)
            value = validated_completion(model, instruction, data, lambda v, packet=packet, unavailable=finding["unavailable_evidence"]: validate_advice(v, packet, unavailable, final_review=True))
            if finding["unavailable_evidence"] and value["verdict"] != "inconclusive":
                raise ValueError("Final review ignored unavailable evidence")
            value = verification_policy(value)
            value.update(finding_id=finding["id"], focus=finding["hypothesis"]["module"], packet=packet)
            finding.update(review_status="reviewed", review=value)
            decisions.append(value)
        except BudgetExhausted as exc:
            finding.update(review_status="budget_exhausted", review_error=str(exc))
            incomplete = True
    # Evidence strength and goal relevance are defensible; degree is not severity or ROI.
    words = set(store.context["payload"]["goal"].lower().split())
    def priority(f):
        advice = f.get("review", f.get("assessment", {}))
        relevance = len(words.intersection((f["hypothesis"]["statement"] + " " + f["hypothesis"]["module"]).lower().split()))
        return (f.get("review_status") != "reviewed", {"supported": 0, "inconclusive": 1, "contradicted": 2}.get(advice.get("verdict"), 3), -relevance, f["id"])
    findings.sort(key=priority)
    decisions = [f["review"] for f in findings if f.get("review")]
    records = store.results()
    queries = [q for r in records for q in r["queries"]]
    evidence = {eid: ev for r in records for eid, ev in r["evidence"].items()}
    traces = [store.read(str(p.relative_to(store.root))) for p in sorted(store.root.glob("investigation/models/*.json"))]
    materializations = [m for r in records for m in r["materializations"]]
    coverage = dict(snapshot["coverage"])
    for record in records:
        coverage.update(record.get("coverage", {}))
    report = {"id": store.root.name, "snapshot": snapshot["id"], "goal": store.context["payload"]["goal"],
        "status": "partial" if incomplete else "review_draft", "stop_reason": reason,
        "mode": "offline deterministic review" if store.config["offline"] else "adaptive model-assisted review",
        "input": snapshot.get("input", {}), "coverage": coverage, "warnings": snapshot.get("warnings", []),
        "findings": findings, "decisions": decisions, "queries": queries, "evidence": evidence,
        "knowledge": knowledge, "materializations": materializations, "errors": [],
        "metrics": {"queries": store.usage().get("queries", 0), "llm_calls": store.usage().get("models", 0)},
        "priority_method": "Independent review, supported evidence, then explicit goal relevance; no measured severity or ROI is inferred.",
        "report_directory": str(store.root), "plan_index": "investigation-plan.json"}
    for finding in findings:
        if finding.get("knowledge"):
            report["knowledge"] = finding["knowledge"]
    store.write("investigation.json", report)
    store.write("model-trace.json", traces)
    # Authoritative per-task logs remain immutable; the index points to each activity stream.
    store.write("investigation/activity-index.json", {"streams": [str(p.relative_to(store.root)) for p in sorted(store.root.glob("investigation/activity/*/events.log"))]})
    return {"status": report["status"], "investigation": {"path": "investigation.json"}, "findings": len(findings), "reviewed": len(decisions)}
