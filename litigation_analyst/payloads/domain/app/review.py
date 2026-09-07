"""Deterministic rendering of model assessments beside verified source excerpts."""

from dataclasses import asdict
import hashlib
from ..models import DraftReport
from ..evidence.assistant import EvidenceAssistant


def build_review(state, store, goal):
    data = state["data"]
    identifier = data["investigation_id"]
    evidence = store.evidence_for(identifier)
    hypotheses = list(data["hypotheses"].values())
    lines = [
        EvidenceAssistant._render("Investigation Review Draft", goal, evidence),
        "## Working hypotheses (inferred assessments)",
        "",
        "Hypothesis assessments are model inferences, not verified conclusions.",
        "",
    ]
    for h in hypotheses:
        lines += [
            f"### {h['id']}: {h['question']}",
            "",
            f"Status: {h['status']}",
            f"Factual basis claimed by agent: {h['factual_basis']}",
            h["assessment"],
            "Supporting evidence: " + ", ".join(h["supporting_evidence"]),
            "Contradictory evidence: " + ", ".join(h["contradictory_evidence"]),
            "Alternative explanations: " + "; ".join(h["alternatives"]),
            "Outstanding enquiries: " + "; ".join(h["outstanding_enquiries"]),
            "",
        ]
    lines += [
        "## Execution and coverage limitations",
        "",
        "Stop reason: " + state["stop_reason"],
        "Only the authorized frozen corpus was examined. Ranked lexical searches are not exhaustive. "
        "No result does not establish absence. Unresolved identities and enquiries require human review.",
        "Complete decision, manual and tool history: case/agent_checkpoint.json.",
        "",
    ]
    report = DraftReport(
        report_id=hashlib.sha256(f"{identifier}|{goal}".encode()).hexdigest()[:24],
        investigation_id=identifier,
        title="Investigation Review Draft",
        review_query=goal,
        status="draft_for_human_review",
        markdown="\n".join(lines),
        evidence_ids=tuple(e.evidence_id for e in evidence),
    )
    store.save_agent_review(report, hypotheses)
    return {
        "report": asdict(report),
        "hypothesis_count": len(hypotheses),
        "stop_reason": state["stop_reason"],
        "successful_queries": sum(
            r["action"].get("name") == "invoke_skill"
            and "result" in r
            and "error" not in r["result"]
            for r in state["records"]
        ),
        "failed_queries": sum("error" in r.get("result", {}) for r in state["records"]),
        "actual_devices": [],
    }
