"""Deterministic rendering of model assessments beside verified source excerpts."""

from dataclasses import asdict
import hashlib
from ..models import DraftReport
from .report_sections import examination_summary
from .findings import narrative_sections


def build_review(state, store, goal):
    data = state["data"]
    identifier = data["investigation_id"]
    evidence = store.evidence_for(identifier)
    hypotheses = list(data["hypotheses"].values())
    evidence_ids = {e.evidence_id for e in evidence}
    for hypothesis in hypotheses:
        if (
            not set(
                hypothesis["supporting_evidence"] + hypothesis["contradictory_evidence"]
            )
            <= evidence_ids
        ):
            raise ValueError(
                "hypothesis cites evidence absent from the verified ledger"
            )
    lines = examination_summary(
        evidence, hypotheses, state["records"], state["stop_reason"]
    )
    lines += [
        "Evidence provenance includes normalized SHA-256 hashes and exact offsets in the linked evidence appendix.",
        "",
    ]
    if not any(
        r.get("result", {}).get("provenance") == "observed_graph_query"
        for r in state["records"]
    ):
        lines += ["No successful graph examination was recorded.", ""]
    lines += narrative_sections(data, evidence)
    lines += ["## Working hypotheses (inferred assessments)", ""]
    if not hypotheses:
        lines += [
            "No structured hypotheses were recorded. No hypothesis findings can be reported.",
            "",
        ]
    if hypotheses:
        lines += [
            f"{len(hypotheses)} working hypotheses are retained in the checkpoint, including revisions and outstanding enquiries. Only reviewed findings appear above.",
            "",
        ]
    lines += [
        "## Audit exhibits",
        "",
        "See [exact source passages](evidence_appendix.md), [graph examinations](graph_appendix.md), and case/agent_checkpoint.json for complete action records.",
        "",
    ]
    lines += [
        "## Recommended human follow-up",
        "",
        "- Check quoted passages against originals and surrounding correspondence.",
        "- Resolve ambiguous identities, chronology, and missing or unreadable sources.",
        "- Test ordinary explanations and seek contradictory evidence before drawing conclusions.",
        "- Revisit enquiries left incomplete by execution limits; this is a recommendation, not work already performed.",
        "",
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
