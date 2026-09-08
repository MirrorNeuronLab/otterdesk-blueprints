import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def setup_run(tmp_path, monkeypatch, architecture_paths):
    from domain.adaptive_planning import initialize_investigation
    from domain.investigation_store import write_json
    from domain.graph import QuerySession
    from domain import evidence_tasks
    cfg = json.loads((Path(__file__).parents[2] / "software_architecture_advisor/config/default.json").read_text())
    context = {"run_dir": str(tmp_path), "config": cfg, "payload": {"goal": "Review payment retry boundaries"}}
    text = "def retry_payment():\n    charge_gateway()\n# intentionally local orchestration\n"
    digest = hashlib.sha256(text.encode()).hexdigest()
    source = {"text": text, "sha256": digest}
    snapshot = {"id": "abc123", "modules": ["payments"], "sources": {"payments.py": digest}, "coverage": {"source_files": 1}, "warnings": []}
    write_json(tmp_path / "snapshot.json", snapshot)
    write_json(tmp_path / "evidence/snapshots/abc123/sources.json", {"payments.py": source})
    (tmp_path / "events.log").write_text("")
    payload, _ = initialize_investigation(context)
    ev = {"id": "E1", "path": "payments.py", "line_start": 1, "line_end": 3, "text": text, "sha256": digest, "kind": "observed_source"}
    class Query:
        def __init__(self, *args, **kwargs):
            self.evidence = {"E1": ev}
            self.receipts = []
            self.materializations = []
            self.layers = None
            self.manifest = snapshot
        def query(self, tool, module=""):
            q = {"id": "Q1", "tool": tool, "status": "ok", "rows": [{"source": "payments", "target": "gateway", "evidence_id": "E1"}],
                 "params": {"module": module}, "query": "MATCH admitted", "elapsed_ms": 1, "result_sha256": "hash"}
            q["raw_result"] = {"rows": q["rows"]}
            q["result_sha256"] = hashlib.sha256(json.dumps(q["raw_result"], sort_keys=True).encode()).hexdigest()
            self.receipts.append(q)
            return q
        def semantic(self, text, modules, purpose):
            q = self.query("semantic", modules[0])
            q.update(search_text=text, purpose=purpose)
            return q
        evidence_ids = QuerySession.evidence_ids
    monkeypatch.setattr(evidence_tasks, "QuerySession", Query)
    # packet construction uses only persisted evidence; retain the real packet implementation.
    Query.packet = QuerySession.packet
    return context, payload["context"]


def scripted_model(monkeypatch, *, inconclusive=False):
    from domain.model import JsonModel
    from domain.investigator import offline_assessment
    calls = []
    def complete(self, instruction, data):
        self.calls.append({"status": "ok", "stage": "scripted"})
        calls.append(data)
        if data.get("round_planner"):
            revision = data["revision"]
            if revision == 2:
                return {"decision": "stop", "rationale": "Counter-evidence resolved the question", "hypotheses": []}
            return {"decision": "execute", "rationale": "Follow the new counter-evidence" if revision else "Inspect retry boundaries", "hypotheses": [{
                "id": "H01", "module": "payments", "family": "resilience", "statement": "Retry may repeat an external charge",
                "semantic_query": "retry external charge", "counter_query": "intentional local orchestration",
                "graph_tools": ["calls"] if not revision else ["state", "tests"],
                "evidence_ids": [] if not revision else data["prior_findings"][0]["query_ids"][:1],
                "expected_information": "Determine whether existing safeguards contradict duplicate-charge risk"}]}
        value = offline_assessment(data["hypothesis"], data["packet"])
        value.update(action_kind="verify", recommendation="Characterize retry_payment external effects before changing the boundary.",
                     next_action="Inject a failure after charge_gateway, retry the same operation, and record charge counts.",
                     counter_evidence=[{"text": "The source documents intentional local orchestration.", "evidence_ids": ["E1"]}])
        return value
    monkeypatch.setattr(JsonModel, "complete", complete)
    return calls


def run_round(context, ref, decision):
    from domain import evidence_tasks
    handlers = {"query_architecture_graph": evidence_tasks.query_graph, "search_architecture_evidence": evidence_tasks.search_evidence,
                "assess_architecture_hypothesis": evidence_tasks.assess_hypothesis, "summarize_architecture_round": evidence_tasks.summarize_round}
    done = set()
    for node in decision["child_plan"]["steps"]:
        assert set(node["needs"]) <= done
        handlers[node["template"]](context, {"context": ref, **node["input"]})
        done.add(node["id"])


def test_two_rounds_change_the_graph_and_publish_cited_review(setup_run, monkeypatch):
    from domain.adaptive_planning import plan_architecture
    from domain.reporting import publish_review
    context, ref = setup_run
    calls = scripted_model(monkeypatch)
    work = lambda revision: {"context": ref, "_child": {"revision": revision}}
    first = plan_architecture(context, work(0))
    run_round(context, ref, first)
    assert len([c for c in calls if c.get("round_planner")]) == 1
    second = plan_architecture(context, work(1))
    assert first["child_plan"]["steps"] != second["child_plan"]["steps"]
    assert calls[-1]["prior_findings"][0]["assessment"]["counter_evidence"]
    run_round(context, ref, second)
    stopped = plan_architecture(context, work(2))
    assert stopped["child_plan"]["decision"] == "stop"
    publish_review(context)
    root = Path(context["run_dir"])
    report = json.loads((root / "report.json").read_text())
    assert report["findings"][0]["revision"] == 2
    assert len(report["decisions"]) == 1
    assert len({q["id"] for q in report["queries"]}) == len(report["queries"])
    text = (root / "report.md").read_text()
    for section in ["Executive summary", "Architecture overview", "Prioritized findings", "Phased implementation roadmap", "Coverage and limitations"]:
        assert section in text
    assert "retry_payment" in text and "#evidence-e1" in text
    previous_calls = len(calls)
    assert plan_architecture(context, work(2)) == stopped
    assert len(calls) == previous_calls


def test_global_budget_preserves_final_review_reserve(setup_run):
    from domain.investigation_store import InvestigationStore, BudgetExhausted
    store = InvestigationStore(setup_run[0]["run_dir"])
    for _ in range(24):
        store.reserve("models")
    with pytest.raises(BudgetExhausted):
        store.reserve("models")
    for _ in range(6):
        store.reserve("models", final=True)
    with pytest.raises(BudgetExhausted):
        store.reserve("models", final=True)


def test_changed_artifact_or_invented_citation_is_rejected(setup_run):
    from domain.investigation_store import InvestigationStore
    from domain.adaptive_planning import validate_round
    context, ref = setup_run
    store = InvestigationStore(context["run_dir"])
    Path(context["run_dir"], "investigation-context.json").write_text("{}")
    with pytest.raises(ValueError, match="hash"):
        store.load_ref(ref)
    with pytest.raises(ValueError):
        validate_round({"decision": "execute", "rationale": "inspect", "hypotheses": [{"id": "H01", "module": "invented"}]}, {"modules": ["payments"]}, [], context["config"]["investigation"])


def test_model_response_replay_does_not_spend_budget_twice(setup_run, monkeypatch):
    from domain.investigation_store import InvestigationStore, RecordedModel
    from domain.model import JsonModel
    context, _ = setup_run
    def complete(self, instruction, data):
        self.calls.append({"status": "ok"})
        return {"result": "grounded"}
    monkeypatch.setattr(JsonModel, "complete", complete)
    store = InvestigationStore(context["run_dir"])
    assert RecordedModel(store, "same").complete("instruction", {}) == {"result": "grounded"}
    assert RecordedModel(store, "same").complete("instruction", {}) == {"result": "grounded"}
    assert store.usage()["models"] == 1
    with pytest.raises(ValueError, match="context changed"):
        RecordedModel(store, "same").complete("different", {})


def test_packet_mutation_cannot_pass_publication(setup_run, monkeypatch):
    from domain.adaptive_planning import plan_architecture
    from domain.reporting import verify_evidence
    context, ref = setup_run
    scripted_model(monkeypatch)
    for revision in range(2):
        result = plan_architecture(context, {"context": ref, "_child": {"revision": revision}})
        run_round(context, ref, result)
    plan_architecture(context, {"context": ref, "_child": {"revision": 2}})
    root = Path(context["run_dir"])
    report = json.loads((root / "investigation.json").read_text())
    report["decisions"][0]["packet"]["passages"][0]["text"] = "Invented evidence"
    with pytest.raises(ValueError, match="reviewed decisions|frozen evidence"):
        verify_evidence(report, root)


def test_deadline_produces_explicitly_incomplete_report(setup_run, monkeypatch):
    from domain.adaptive_planning import plan_architecture
    from domain.investigation_store import InvestigationStore
    import time
    context, ref = setup_run
    store = InvestigationStore(context["run_dir"])
    monkeypatch.setattr(time, "time", lambda: store.context["deadline"] + 1)
    result = plan_architecture(context, {"context": ref, "_child": {"revision": 0}})
    assert result["child_plan"]["decision"] == "stop"
    assert result["child_plan"]["output"]["status"] == "partial"


def test_unavailable_evidence_cannot_be_promoted_by_review(setup_run, monkeypatch):
    from domain.evidence_tasks import validate_advice
    monkeypatch.setattr("domain.evidence_tasks.validate_assessment", lambda value, packet: value)
    with pytest.raises(ValueError, match="inconclusive"):
        validate_advice({"verdict": "supported"}, {}, ["state graph unavailable"])


@pytest.mark.parametrize("saved_response", [True, False])
def test_partial_model_replay_rehydrates_sdk_receipt_without_reserving_again(setup_run, monkeypatch, saved_response):
    from domain.investigation_store import InvestigationStore, RecordedModel
    from domain.model import JsonModel
    context, _ = setup_run
    store = InvestigationStore(context["run_dir"])
    instruction, data = "review", {"goal":"payments"}
    digest = hashlib.sha256(json.dumps([instruction, data], sort_keys=True).encode()).hexdigest()
    store.reserve("models")
    store.write("investigation/models/recovery-000.json", {"request_hash":digest,"status":"started"})
    checked = []
    memory = SimpleNamespace(has_durable_response=lambda invocation: checked.append(invocation) or saved_response)
    monkeypatch.setattr(JsonModel, "memory_session", lambda self: memory)
    def rehydrate(self, instruction, data):
        self.calls.append({"status":"ok", "replayed":True})
        return {"result":"saved verified answer"}
    monkeypatch.setattr(JsonModel, "complete", rehydrate)
    if saved_response:
        assert RecordedModel(store, "recovery").complete(instruction, data) == {"result":"saved verified answer"}
        assert store.read("investigation/models/recovery-000.json")["status"] == "completed"
    else:
        with pytest.raises(RuntimeError, match="no durable response"):
            RecordedModel(store, "recovery").complete(instruction, data)
    assert checked == ["recovery-001"]
    assert store.usage()["models"] == 1


def test_planner_registry_constrains_revisions_and_preserves_verified_actions(architecture_paths):
    from domain.model import response_schema
    from domain.evidence_tasks import verification_policy
    data = {"round_planner":True, "candidates":["payments"], "families":{"resilience":[]}, "tools":["calls"], "max_hypotheses":3, "hypothesis_registry":[]}
    schema = response_schema(data)
    assert schema["properties"]["retirements"]["maxItems"] == 0
    assert schema["properties"]["hypotheses"]["items"]["properties"]["evidence_ids"]["maxItems"] == 0
    data["hypothesis_registry"] = [{"id":"H01", "query_ids":["r02-Q1"], "evidence_ids":["E1"]}]
    schema = response_schema(data)
    retirement = schema["properties"]["retirements"]["items"]["properties"]
    assert retirement["id"]["enum"] == ["H01"]
    assert retirement["evidence_ids"]["items"]["enum"] == ["E1", "r02-Q1"]
    advice = verification_policy({"action_kind":"verify", "recommendation":"Characterize retry_payment.", "next_action":"Inject a gateway timeout after charge and retry the identical order.", "acceptance_test":"Assert one gateway charge and one ledger row for the order.", "rollback":"Remove temporary fault injection.", "missing_evidence":["Gateway deduplication contract"]})
    assert "Inject a gateway timeout after charge" in advice["next_action"]
    assert "one gateway charge and one ledger row" in advice["acceptance_test"]
