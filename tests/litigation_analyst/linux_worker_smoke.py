import json
from pathlib import Path
from domain.intake import prepare_sources
from domain.indexing import build_indexes, validate_indexes
from domain.research import investigate
from domain.reporting import write_review

root = Path("/tmp/case-smoke")
root.mkdir()
source = root / "input"
source.mkdir()
(source / "notice.eml").write_text(
    "From: xyz@example.test\nTo: reviewer@example.test\nSubject: Cybersecurity approval\nDate: Tue, 01 Sep 2026 10:00:00 +0000\n\nRoutine cybersecurity approval review requires context.\n"
)
config = json.loads(Path("/blueprint/config/default.json").read_text())
context = {
    "run_dir": root / "run",
    "config": config,
    "payload": {
        "input_folder": str(source),
        "goal": "Review cybersecurity approval and ordinary explanations.",
    },
}


class Model:
    model = "scripted-linux-smoke"
    last_usage = {}

    def completion_text(self, system, user):
        state = json.loads(user)
        history = state["history"]
        i = len(history)
        if i == 0:
            name, args = "read_skill", {"skill": "mirrorneuron.graph.analysis"}
        elif i == 1:
            name, args = (
                "invoke_skill",
                {
                    "skill": "mirrorneuron.graph.analysis",
                    "operation": "query",
                    "arguments": {"rgql": "MATCH (e:Email) RETURN e.source_id LIMIT 5"},
                },
            )
        elif i == 2:
            assert "error" not in history[-1]["result"], history[-1]
            name, args = "read_skill", {"skill": "mirrorneuron.document.reading"}
        elif i == 3:
            name, args = (
                "invoke_skill",
                {
                    "skill": "mirrorneuron.document.reading",
                    "operation": "search",
                    "arguments": {"query": "cybersecurity"},
                },
            )
        elif i == 4:
            ids = [p["evidence_id"] for p in history[-1]["result"]["passages"]]
            assert ids
            name, args = (
                "update_hypothesis",
                {
                    "id": "notice",
                    "question": "Did XYZ know about the issue?",
                    "factual_basis": "A message mentions cybersecurity approval; identity remains unresolved.",
                    "supporting_evidence": ids,
                    "contradictory_evidence": [],
                    "alternatives": ["Routine review responsibilities."],
                    "status": "inconclusive",
                    "assessment": "Context and chronology need human review.",
                    "outstanding_enquiries": ["Verify identity."],
                    "parent_id": None,
                },
            )
        else:
            name, args = (
                "finish",
                {"reason": "Refer unresolved context to a human reviewer."},
            )
        return json.dumps(
            {"name": name, "arguments": args, "reason": "Follow the observed lead."}
        )


prepare_sources(context)
build_indexes(context)
investigate(context, llm_client=Model())
validate_indexes(root / "run/case", "case")
write_review(context)
investigate(context, llm_client=Model())
state = json.loads((root / "run/case/agent_checkpoint.json").read_text())
assert state["stop_reason"] == "completed"
assert len(state["records"]) == 6
assert "Routine cybersecurity" in (root / "run/final_report.md").read_text()
print(
    "PASS: actual Linux RGX ingestion/query, wheel manuals, adaptive loop, citations, replay"
)
