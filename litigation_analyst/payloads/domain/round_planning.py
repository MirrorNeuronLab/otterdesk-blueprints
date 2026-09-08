"""LLM-directed litigation enquiries compiled into admitted child tasks."""
import time
from mn_sdk.child_workflow import round_plan, stop_plan
from .app.planning import object_schema, validate
from .round_state import open_round, read, save, checkpoint, finish
from .round_model import complete
from .graph_queries import QUERIES

TEXT = {"type": "string", "minLength": 1, "maxLength": 500}
ENQUIRY = object_schema({
    "id": {"type": "string", "pattern": "^H[0-9]{2}$"},
    "question": TEXT, "support_query": TEXT, "counter_query": TEXT,
    "expected_information": TEXT,
    "graph_tools": {"type": "array", "maxItems": 2, "uniqueItems": True, "items": {"enum": sorted(QUERIES)}},
})


def plan_round(context, work, *, llm_client=None):
    root, frozen = open_round(context, work)
    revision = work["_child"]["revision"]
    name = f"case/rounds/plan-{revision:02d}.json"
    if (root / name).exists():
        return read(root / name)
    cfg = frozen["config"]["dynamic_investigation"]
    reason = None
    if (root / "case/cancel.request").exists():
        reason = "cancelled"
    elif time.time() >= frozen["deadline"]:
        reason = "investigation_deadline_reached"
    elif revision >= cfg["max_rounds"]:
        reason = "maximum_rounds_reached"
    if reason:
        value = {"decision": "stop", "rationale": reason, "hypotheses": []}
    else:
        schema = object_schema({"decision": {"enum": ["execute", "stop"]}, "rationale": TEXT,
            "hypotheses": {"type": "array", "maxItems": cfg["hypotheses_per_round"], "items": ENQUIRY}})
        previous = [] if not revision else read(root / f"case/rounds/summary-{revision:02d}.json")["findings"]
        value = complete(root, frozen, f"plan-{revision:02d}", "plan", 
            "Choose execute or stop. Execute selects concrete falsifiable enquiries with distinct support and counter searches. "
            "Select zero to two named graph_tools from the admitted views only when they reduce uncertainty. Never write RGQL. "
            "Use stable Hnn IDs when revising earlier enquiries. Change searches based on prior evidence and unresolved issues. "
            "Stop requires a concrete reason and an empty hypotheses list. Do not stop before examining evidence. ",
            {"goal": frozen["payload"]["goal"], "revision": revision, "prior_findings": previous,
             "remaining_rounds": cfg["max_rounds"] - revision, "graph_views": QUERIES}, schema, llm_client)
        if value["decision"] == "execute":
            if not value["hypotheses"] or len({h["id"] for h in value["hypotheses"]}) != len(value["hypotheses"]):
                raise ValueError("Execute requires distinct enquiries")
            from .round_tasks import validate_graph_query
            for h in value["hypotheses"]:
                if h["support_query"].strip().casefold() == h["counter_query"].strip().casefold():
                    raise ValueError("Support and counter-evidence searches must differ")
                for query in h["graph_tools"]:
                    validate_graph_query(QUERIES[query])
            earlier = [read(p)["proposal"] for p in sorted((root / "case/rounds").glob("proposal-*.json"))]
            signatures = {(h["question"], h["support_query"], h["counter_query"], tuple(h["graph_tools"])) for p in earlier for h in p["hypotheses"]}
            if all((h["question"], h["support_query"], h["counter_query"], tuple(h["graph_tools"])) in signatures for h in value["hypotheses"]):
                value = {"decision": "stop", "rationale": "no_new_evidence_work_proposed", "hypotheses": []}
        elif value["hypotheses"] or not revision:
            raise ValueError("Planner cannot skip initial evidence collection or execute work while stopping")
    save(root, f"case/rounds/proposal-{revision:02d}.json", {"proposal": value})
    if value["decision"] == "stop":
        result = stop_plan(revision=revision, reason=value["rationale"], output=finish(root, frozen, value["rationale"]))
    else:
        steps, previous = [], []
        for h in value["hypotheses"]:
            prefix = f"r{revision+1:02d}-{h['id']}"
            task = save(root, f"case/rounds/tasks/{prefix}.json", {"hypothesis": h, "prefix": prefix})
            for suffix, template in (("evidence", "collect_litigation_evidence"), ("assessment", "assess_litigation_hypothesis"), ("review", "review_litigation_finding")):
                key = f"{h['id']}-{suffix}"
                steps.append({"id": key, "template": template, "needs": previous, "input": {"task": task}})
                previous = [key]
        task = save(root, f"case/rounds/tasks/summary-{revision+1:02d}.json", {"revision": revision+1})
        steps.append({"id": "summarize", "template": "summarize_litigation_round", "needs": previous, "input": {"task": task}})
        result = round_plan(revision=revision, steps=steps, rationale=f"Execute committed litigation enquiries for round {revision+1}", evidence_refs=[])
    save(root, name, result)
    return result
