"""Bounded evidence collection and separate hypothesis/review specialists."""
from dataclasses import asdict
import re
from mn_sdk.blueprint_support import source_manifest
from .round_state import task_input, read, save, checkpoint
from .round_model import complete
from .graph_queries import QUERIES
from .indexing import validate_indexes
from .evidence.store import EvidenceStore
from .app.skill_bindings import bind_skills, DOC, GRAPH
from .app.activity import observe_action
from .app.planning import object_schema, HYPOTHESIS, validate
from .app.findings import REPORT, REVIEW, submit_report, review_report
from .app.prompt_context import investigation_history


def validate_graph_query(query):
    masked = re.sub(r"'(?:[^'\\]|\\.)*'", "''", query)
    limits = re.findall(r"\bLIMIT\s+(\d+)\b", masked, re.I)
    if not limits or any(not 1 <= int(n) <= 50 for n in limits) or re.search(r"\b(CREATE|DELETE|SET|DROP|INSERT|UPDATE|MERGE|REMOVE)\b", masked, re.I):
        raise ValueError("Only read-only graph queries with LIMIT <=50 are admitted")


def collect_evidence(context, work, *, llm_client=None):
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-evidence.json"
    if (root / name).exists():
        return {"evidence": save(root, name, read(root / name))}
    case = root / "case"
    corpus, _ = validate_indexes(case, frozen["config"]["investigation"]["access_scope"])
    store = EvidenceStore(case / "evidence.sqlite3")
    runtime = bind_skills(case, corpus, store, frozen["investigation_id"],
                         [d["name"] for d in source_manifest(__file__)["skill_dependencies"]])
    records = []
    h = task["hypothesis"]
    operations = [(DOC, "search", {"query": h[p + "_query"], "top_k": min(3, frozen["config"]["investigation"]["top_k"])}, p) for p in ("support", "counter")]
    operations += [(GRAPH, "query", {"rgql": QUERIES[q]}, "graph") for q in h["graph_tools"]]
    for skill, operation, arguments, purpose in operations:
        if skill == GRAPH:
            validate_graph_query(arguments["rgql"])
        runtime.read_skill(skill)
        action = {"name": "invoke_skill", "arguments": {"skill": skill, "operation": operation, "arguments": arguments}, "reason": h["expected_information"]}
        result = observe_action(action, {"records": records + [{}]}, lambda *_: runtime.invoke_skill(skill, operation, arguments))
        records.append({"action": action, "result": result, "purpose": purpose})
    # Exact spans are already verified by the shared skill binding and in the ledger.
    ids = list(dict.fromkeys(p["evidence_id"] for r in records for p in r["result"].get("passages", [])))
    ref = save(root, name, {"hypothesis": h, "records": records, "evidence_ids": ids})
    return {"evidence": ref}


def assess_hypothesis(context, work, *, llm_client=None):
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-assessment.json"
    if (root / name).exists():
        return {"assessment": save(root, name, read(root / name))}
    collected = read(root / f"case/rounds/{task['prefix']}-evidence.json")
    store = EvidenceStore(root / "case/evidence.sqlite3")
    allowed = set(collected["evidence_ids"])
    # Focused complete spans fit a review unit. Omitted spans remain in the ledger.
    spans, remaining = [], 2000
    for e in store.evidence_for(frozen["investigation_id"]):
        if e.evidence_id in allowed and e.source_id not in frozen["source_review_flags"] and len(e.text.encode()) <= remaining:
            spans.append(asdict(e)); remaining -= len(e.text.encode())
    visible = {e["evidence_id"] for e in spans}
    schema = object_schema({"hypothesis": HYPOTHESIS, "report": REPORT})
    value = complete(root, frozen, task["prefix"] + "-assess", "assess",
        "Assess the committed enquiry from complete visible passages. Keep its exact hypothesis ID and parent_id null. "
        "Cite only visible evidence IDs. Include ordinary alternatives and outstanding enquiries. "
        "With no visible evidence, return inconclusive and an empty findings list. "
        "Propose at most one concise report finding; use the supplied finding_id. Findings are inferred assessments. "
        "Graph observations are navigation aids, not proof. State unexamined/omitted evidence limits.",
        {"enquiry": task["hypothesis"], "finding_id": task["prefix"], "evidence": spans,
         "omitted_passages": len(allowed - visible),
         "graph_observations": investigation_history([r for r in collected["records"] if r["purpose"] == "graph"], max_bytes=2000),
         "search_coverage": [{"purpose": r["purpose"], "passage_count": len(r["result"].get("passages", [])), "evidence_ids": [p["evidence_id"] for p in r["result"].get("passages", []) if p["evidence_id"] in visible]} for r in collected["records"]]}, schema, llm_client)
    h = value["hypothesis"]
    if h["id"] != task["hypothesis"]["id"] or h["parent_id"] is not None:
        raise ValueError("Assessment changed the committed hypothesis identity")
    cited = set(h["supporting_evidence"] + h["contradictory_evidence"])
    cited.update(e for f in value["report"]["findings"] for e in f["evidence_ids"])
    if not cited <= visible or (h["status"] in ("supported", "contradicted") and not cited):
        raise ValueError("Assessment cites unavailable evidence")
    if any(f["id"] != task["prefix"] for f in value["report"]["findings"]):
        raise ValueError("Finding identity must match committed task")
    data = {"source_review_flags": frozen["source_review_flags"]}
    submit_report(data, value["report"], store, frozen["investigation_id"])
    return {"assessment": save(root, name, value)}


def review_finding(context, work, *, llm_client=None):
    root, frozen, task = task_input(context, work)
    name = f"case/rounds/{task['prefix']}-review.json"
    if (root / name).exists():
        return {"review": save(root, name, read(root / name))}
    assessment = read(root / f"case/rounds/{task['prefix']}-assessment.json")
    store = EvidenceStore(root / "case/evidence.sqlite3")
    data = {"source_review_flags": frozen["source_review_flags"]}
    submit_report(data, assessment["report"], store, frozen["investigation_id"])
    cited = {i for f in assessment["report"]["findings"] for i in f["evidence_ids"]}
    value = complete(root, frozen, task["prefix"] + "-review", "review",
        "Independently review the proposed finding against every complete cited passage. Accept only wording "
        "supported by these sources, preserving identity uncertainty, competing explanations and incomplete coverage. "
        "Reject overstatement, missing context, unsupported dates or allegations; explain issues concisely. "
        "Accept only supplied finding IDs. You cannot add evidence or rewrite the finding.",
        {"report": assessment["report"], "hypothesis": assessment["hypothesis"],
         "evidence": [asdict(e) for e in store.evidence_for(frozen["investigation_id"]) if e.evidence_id in cited]}, REVIEW, llm_client)
    review_report(data, value)
    return {"review": save(root, name, value)}


def summarize_round(context, work, *, llm_client=None):
    root, frozen, task = task_input(context, work)
    state = checkpoint(root, frozen)
    findings = [{"id": h["id"], "question": h["question"], "status": h["status"],
                 "assessment": h["assessment"], "counter_evidence": h["contradictory_evidence"],
                 "outstanding_enquiries": h["outstanding_enquiries"]}
                for h in state["data"]["hypotheses"].values()]
    name = f"case/rounds/summary-{task['revision']:02d}.json"
    return {"summary": save(root, name, {"findings": findings, "review": state["data"]["report_review"]})}
