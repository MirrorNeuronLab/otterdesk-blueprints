"""Opt-in Linux worker smoke: real RGX, real SDK handlers, scripted or live models.

Run in the advisor worker image with the blueprint mounted at /blueprints and
its payload root on PYTHONPATH. The test driver executes committed DAGs; production
scheduling is separately exercised by Core's child_workflow_test.exs.
"""
import argparse
import importlib
import json
import uuid
from pathlib import Path

from mn_sdk.step_runtime import StepContext
from domain.intake import capture_input
from domain.adaptive_planning import initialize_investigation
from domain.reporting import publish_review
from domain.model import JsonModel
from domain.investigator import offline_assessment
from runtime.runtime import runtime_context_for_step


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", required=True)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    run_id = "dynamic-smoke-" + uuid.uuid4().hex[:10]
    blueprint = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    cfg = json.loads((blueprint / "config/default.json").read_text())
    cfg["graph"]["binary"] = "/opt/mn-graph-engine/bin/rgx"
    cfg["embedding"]["mode"] = "hash"  # Isolate graph/planning/report validation from embedding-provider setup.
    cfg["output_folder"] = args.output
    inputs = {"input_folder": str(blueprint / "examples/sample_repository"),
              "graph_export": str(blueprint / "examples/sample_repository/architecture-facts.json"),
              "goal": "Review retry and transaction boundaries in payments.payment_service"}
    calls = []
    if not args.live:
        def scripted(self, instruction, data):
            self.calls.append({"status": "ok", "mode": "scripted smoke"})
            calls.append(data)
            if data.get("round_planner"):
                revision = data["revision"]
                if revision == 2:
                    return {"decision": "stop", "rationale": "Two rounds collected support and counter-evidence", "hypotheses": []}
                prior = data["prior_findings"]
                return {"decision": "execute", "rationale": "Examine retry guarantees" if not revision else "Check source declarations against intentional orchestration", "hypotheses": [{
                    "id": "H01", "module": "payments.payment_service", "family": "resilience",
                    "statement": "Retry may repeat external effects across the local transaction boundary",
                    "semantic_query": "retry charge gateway transaction", "counter_query": "intentional local orchestration transaction",
                    "graph_tools": ["dependencies", "calls"] if not revision else ["symbols", "tests"],
                    "evidence_ids": prior[0]["query_ids"][:1] if prior else [],
                    "expected_information": "Distinguish retry behavior from a claimed need for a process split"}]}
            value = offline_assessment(data["hypothesis"], data["packet"])
            value.update(action_kind="verify", recommendation="Characterize retry_payment before changing the payment-service boundary.",
                         next_action="Fail after the gateway effect, retry the same payment, and record gateway and ledger effects.")
            return value
        JsonModel.complete = scripted
    context = runtime_context_for_step(inputs=inputs, config=cfg, runs_root=args.output, run_id=run_id)
    capture_input(context)
    initialized, _ = initialize_investigation(context)
    context_ref = initialized["context"]
    templates = json.loads((blueprint / "workflow.json").read_text())["child_workflows"]["investigate_architecture"]["templates"]
    def invoke(template, step_id, work):
        handler = importlib.import_module(templates[template]["run"]["handler"]).run
        step = StepContext(step_id=step_id, run_id=run_id, config=cfg,
                           idempotency_key=step_id, message={"_mn_step": {"step_input": work}})
        return handler(step, runs_root=args.output).outputs
    graphs = []
    for revision in range(cfg["investigation"]["max_rounds"] + 1):
        work = {"context": context_ref, "_child": {"revision": revision, "round": revision}}
        output = invoke("plan_architecture_round", f"investigate_architecture:p{revision}", work)
        plan = output["child_plan"]
        if plan["decision"] == "stop":
            break
        graphs.append(plan)
        done = set()
        for node in plan["steps"]:
            assert set(node["needs"]) <= done
            invoke(node["template"], f"investigate_architecture:r{revision+1}:{node['id']}",
                   {**work, **node["input"]})
            done.add(node["id"])
    else:
        raise AssertionError("Child failed to stop within the admitted round bound")
    publish_review(context)
    report = json.loads((Path(context["run_dir"]) / "report.json").read_text())
    assert report["queries"] and report["evidence"]
    assert all(f.get("review_status") == "reviewed" for f in report["findings"] if f["status"] == "assessed" and not f.get("retirement") and f.get("review_status") != "budget_exhausted")
    if not args.live:
        assert len(graphs) == 2 and graphs[0]["steps"] != graphs[1]["steps"]
        count = len(calls)
        replay = invoke("plan_architecture_round", f"investigate_architecture:p{revision}", work)
        assert replay == output and len(calls) == count
    print(json.dumps({"status": report["status"], "rounds": len(graphs), "queries": len(report["queries"]),
                      "reviewed": len(report["decisions"]), "report": str(Path(context["run_dir"]) / "report.md")}))


if __name__ == "__main__":
    main()
