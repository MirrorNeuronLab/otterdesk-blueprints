import json
import pytest
from test_litigation_analyst import (
    modules,
    graph_engine_stub,
    make_context,
    ScriptedModel,
    BLUEPRINT,
)
from mn_sdk.blueprints import read_blueprint, resolve_config, compile_blueprint


def case_context(modules, tmp_path):
    folder = tmp_path / "input"
    folder.mkdir()
    (folder / "notice.txt").write_text(
        "Approval notice. Routine duties explain the correspondence."
    )
    context = make_context(tmp_path, folder)
    modules["intake"].prepare_sources(context)
    modules["indexing"].build_indexes(context)
    return context


def test_every_model_decision_has_attributed_guidance_and_phase(modules, tmp_path):
    context = case_context(modules, tmp_path)
    model = ScriptedModel()
    modules["research"].investigate(context, llm_client=model)
    state = json.loads((context["run_dir"] / "case/agent_checkpoint.json").read_text())
    requests = [
        json.loads(r["request"]["messages"][1]["content"])
        for r in state["data"]["model_interactions"]
    ]
    assert {r["phase"] for r in requests} == {"planning", "execution", "report_review"}
    assert all(
        r["guidance"]["citations"] and r["guidance"]["index_sha256"] for r in requests
    )
    assert all(
        "source_url" in c and "sha256" in c
        for r in requests
        for c in r["guidance"]["citations"]
    )
    assert requests[-2]["review_evidence"]
    assert model.calls < 20
    assert (
        len(state["data"]["cycle"]["plans"])
        == len(state["data"]["cycle"]["outcomes"])
        == 1
    )
    assert state["stop_reason"] == "completed"


def test_large_deadline_survives_compilation(modules):
    package = read_blueprint(BLUEPRINT)
    config = resolve_config(package)
    assert config.data["investigation"]["max_model_decisions"] == 5000
    assert config.data["investigation"]["max_skill_invocations"] == 5000
    assert config.data["investigation"]["max_investigation_seconds"] == 99999
    compiled = compile_blueprint(package, config).manifest
    step = next(
        s for s in compiled["workflow"]["steps"] if s["id"] == "investigate_case_evidence"
    )
    assert (
        "timeout_seconds" in step["control"]
        and step["control"]["timeout_seconds"] == 99999
    )
    serialized = json.dumps(compiled)
    assert "mn-python-sdk-rag" in serialized


def test_unaccepted_findings_are_withheld(modules, tmp_path):
    context = case_context(modules, tmp_path)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    path = context["run_dir"] / "case/agent_checkpoint.json"
    state = json.loads(path.read_text())
    state["data"]["report_draft"]["findings"][0]["assessment"] = (
        "UNSUPPORTED ACCUSATION"
    )
    state["data"]["report_review"] = {
        "accepted_ids": [],
        "issues": ["Evidence does not establish allegation."],
    }
    path.write_text(json.dumps(state))
    modules["reporting"].write_review(context)
    text = (context["run_dir"] / "final_report.md").read_text()
    assert "UNSUPPORTED ACCUSATION" not in text
    assert "Evidence does not establish allegation" in text
    assert (context["run_dir"] / "evidence_appendix.md").exists()
    assert (context["run_dir"] / "graph_appendix.md").exists()


def test_report_rejects_unknown_citations_and_flagged_sources(modules, tmp_path):
    from domain.app.findings import submit_report
    from domain.evidence.store import EvidenceStore

    context = case_context(modules, tmp_path)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    state = json.loads((context["run_dir"] / "case/agent_checkpoint.json").read_text())
    store = EvidenceStore(context["run_dir"] / "case/evidence.sqlite3")
    data = state["data"]
    report = json.loads(json.dumps(data["report_draft"]))
    source_id = store.evidence_for(data["investigation_id"])[0].source_id
    data["source_review_flags"] = {source_id: "Potential privilege."}
    with pytest.raises(ValueError, match="handling review"):
        submit_report(data, report, store, data["investigation_id"])
    report["findings"][0]["evidence_ids"] = ["invented"]
    with pytest.raises(ValueError, match="unverified"):
        submit_report(data, report, store, data["investigation_id"])


def test_guidance_changes_reject_resume(modules, tmp_path, monkeypatch):
    from domain.app import agentic

    context = case_context(modules, tmp_path)
    modules["research"].investigate(context, llm_client=ScriptedModel())
    original = agentic.InvestigationGuidance

    class Changed(original):
        def __init__(self):
            super().__init__()
            self.fingerprint = "changed"

    monkeypatch.setattr(agentic, "InvestigationGuidance", Changed)
    with pytest.raises(ValueError, match="binding mismatch"):
        modules["research"].investigate(context, llm_client=ScriptedModel())
