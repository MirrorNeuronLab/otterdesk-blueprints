from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_SRC = ROOT.parent / "mn-skills" / "blueprint_support_skill" / "src"
AUTONOMOUS_RESEARCH_SRC = ROOT.parent / "mn-skills" / "autonomous_research_skill" / "src"
SDK_SRC = ROOT.parent / "mn-python-sdk"
for path in (SDK_SRC, SUPPORT_SRC, AUTONOMOUS_RESEARCH_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from mn_sdk import expand_manifest_source


def _manifest() -> dict:
    blueprint = ROOT / "research_coscientist"
    source = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    return expand_manifest_source(source, root_dir=blueprint)


def _runner():
    path = ROOT / "research_coscientist" / "payloads" / "runtime" / "runtime.py"
    spec = importlib.util.spec_from_file_location("research_coscientist_runner_tests", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_research_input_normalization_and_query_privacy():
    runner = _runner()
    normalized = runner.normalize_inputs(
        {
            "goal": "Compare cooling-loop controls",
            "domain": "engineering",
            "question": "Which control can be tested first?",
            "constraints": {"no_live_system_changes": True},
        }
    )

    assert normalized["research_goal"] == "Compare cooling-loop controls"
    assert normalized["research_domain"] == "engineering"
    assert normalized["research_question"] == "Which control can be tested first?"
    assert runner.build_public_queries(normalized)

    private = runner.normalize_inputs(
        {"research_goal": "confidential raw_document_text", "research_domain": "engineering"}
    )
    assert runner.build_public_queries(private) == []


def test_research_prompts_and_fake_run_write_review_only_packet(tmp_path):
    runner = _runner()
    assert runner.PROMPTS.prompt_dir == (
        ROOT / "research_coscientist" / "payloads" / "prompts"
    )
    assert "Research Packet System Prompt" in runner.load_prompt("research-packet-system.md")
    assert "Research Co-Scientist Autonomous Review Task" in runner.load_prompt("research-review-task.md")

    output = tmp_path / "outputs"
    result = runner.run_blueprint(
        inputs={
            "research_goal": "Evaluate a low-risk cooling-loop efficiency hypothesis.",
            "research_domain": "engineering",
            "research_question": "What measurement distinguishes the hypothesis from ambient variation?",
            "scope": "Desk research only.",
            "input_folder": str(ROOT / "research_coscientist" / "examples" / "sample_inputs"),
            "output_folder": str(output),
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs",
        run_id="research-coscientist-test",
    )

    packet = result["final_artifact"]
    assert result["autonomous_research"]["isolation_required"] is True
    assert result["autonomous_research"]["session"]["goal"]["goal_id"].startswith("goal_")
    assert result["autonomous_research"]["session"]["prompts"]
    assert packet["recommended_action"] in runner.RESEARCH_ACTIONS
    assert packet["status"] == "review_ready"
    assert packet["source_refs"]
    assert all(source_ref.startswith(("local:", "web:")) for source_ref in packet["source_refs"])
    assert packet["hypothesis_ledger"]
    assert set(runner.BLOCKED_ACTIONS) <= set(packet["review_boundary"]["blocked_actions"])
    for name in (
        "research_packet.json",
        "research_brief.md",
        "evidence_ledger.json",
        "hypothesis_ledger.json",
        "review_ledger.json",
        "artifact_quality.json",
        "run_health.json",
    ):
        assert (output / name).exists(), name
    json.loads((output / "research_packet.json").read_text(encoding="utf-8"))


def test_bundled_runtime_assets_are_available_and_keep_knowledge_in_sync(monkeypatch):
    runner = _runner()
    asset_root = runner.runtime_asset_root()
    expected_input = asset_root / "examples" / "sample_inputs"

    assert (
        runner.resolve_input_folder({}, {"input_folder": "examples/sample_inputs"}, ROOT / "research_coscientist")
        == expected_input
    )
    documents, document_warnings = runner.load_input_documents(expected_input, {})
    assert documents
    assert not document_warnings

    for relative_path in (
        "ai_co_scientist_inspiration.md",
        "research_coscientist_playbook.md",
        "research_evidence_checklist.md",
        "research_governance_and_retrieval.md",
    ):
        assert (ROOT / "research_coscientist" / "knowledge" / relative_path).read_bytes() == (
            asset_root / "knowledge" / relative_path
        ).read_bytes()
    for relative_path in ("README.md", "SAMPLE_DATASET_MANIFEST.json", "sample_research_notes.md", "sample_research_request.json"):
        assert (ROOT / "research_coscientist" / "examples" / "sample_inputs" / relative_path).read_bytes() == (
            expected_input / relative_path
        ).read_bytes()

    def embedding_failure(**_kwargs):
        raise OSError("embedding service unavailable")

    monkeypatch.setattr(runner, "prepare_blueprint_knowledge_rag", embedding_failure)
    prepared = runner.prepare_evidence_context(
        {"knowledge_rag": {"enabled": True}, "internet_research": {"enabled": False}},
        runner.normalize_inputs(
            {"research_goal": "Compare cooling-loop controls", "input_folder": "examples/sample_inputs"}
        ),
        ROOT / "research_coscientist",
        "bundled-assets-test",
        quick_test=True,
    )

    assert prepared["rag"]["status"] == "local_lexical_fallback"
    assert prepared["rag"]["retrieval_backend"] == "local_lexical_rag"
    assert prepared["rag"]["fallback_active"] is True
    assert prepared["rag"]["citations"]
    assert any("local lexical retrieval" in warning.get("message", "") for warning in prepared["warnings"])


def test_staged_evidence_preparation_keeps_observed_public_sources(monkeypatch):
    runner = _runner()
    inputs = runner.normalize_inputs(
        {
            "research_goal": "Compare cooling-loop controls",
            "research_question": "Which control can be tested first?",
            "input_folder": "examples/sample_inputs",
        }
    )
    source = {
        "source_ref": "web:cooling-controls",
        "url": "https://example.test/cooling-controls",
        "title": "Cooling controls study",
        "snippet": "A measured comparison of cooling control strategies.",
        "status": "observed",
        "skill": "test_browser",
        "query": "cooling controls",
        "retrieved_at": "2026-07-13T00:00:00Z",
        "warning": "",
    }
    monkeypatch.setattr(
        runner,
        "_resolve_runtime_stage_request",
        lambda: (
            {"llm": {"mode": "live"}, "knowledge_rag": {"enabled": False}},
            inputs,
            object(),
            {"previous": {}, "input_source": {}, "llm_mode": "live"},
        ),
    )
    monkeypatch.setattr(runner, "research_public_sources", lambda *_args, **_kwargs: ([source], []))
    monkeypatch.setenv("MN_JOB_ID", "staged-evidence-test")

    response = runner.run_runtime_step("retrieve_and_evaluate_evidence")
    payload = response["workflow_payload"]

    assert payload["sources"] == [source]
    assert payload["evidence"]["usable_public_source_count"] == 1
    assert payload["evidence"]["source_refs"] == [
        "local:README.md",
        "local:SAMPLE_DATASET_MANIFEST.json",
        "local:sample_research_notes.md",
        "local:sample_research_request.json",
        "web:cooling-controls",
    ]


def test_default_run_uses_the_bundled_sample_input(tmp_path):
    runner = _runner()
    output = tmp_path / "outputs"

    result = runner.run_blueprint(
        inputs={"output_folder": str(output)},
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs",
        run_id="bundled-default-test",
    )

    deterministic = result["final_artifact"]["evidence"]["deterministic"]
    assert deterministic["document_count"] >= 2
    assert deterministic["usable_evidence_present"] is True


def test_evidence_free_packet_is_diagnostic_not_review_ready(tmp_path):
    runner = _runner()
    empty_input = tmp_path / "empty-input"
    empty_input.mkdir()
    output = tmp_path / "outputs"

    result = runner.run_blueprint(
        inputs={
            "research_goal": "Evaluate an unsupported research question.",
            "input_folder": str(empty_input),
            "output_folder": str(output),
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs",
        run_id="needs-evidence-test",
    )

    packet = result["final_artifact"]
    quality = json.loads((output / "artifact_quality.json").read_text(encoding="utf-8"))
    brief = (output / "research_brief.md").read_text(encoding="utf-8")
    assert packet["status"] == "needs_evidence"
    assert packet["recommended_action"] == "gather_more_evidence"
    assert packet["source_refs"] == []
    assert packet["provenance_refs"] == ["inputs.json", "events.jsonl", "result.json"]
    assert quality["status"] == "needs_evidence"
    assert any(check["name"] == "usable_evidence_present" and not check["passed"] for check in quality["quality_checks"])
    assert "**Status:** needs_evidence" in brief
    assert "Usable evidence present: No" in brief


def test_research_defaults_use_downloads_and_mirrored_config():
    runner = _runner()
    blueprint = ROOT / "research_coscientist"
    manifest = _manifest()
    config_path = blueprint / "config" / "default.json"
    payload_config_path = blueprint / "payloads" / "config" / "default.json"

    assert runner.DEFAULT_OUTPUT_FOLDER == "~/Downloads/research_coscientist"
    assert config_path.read_bytes() == payload_config_path.read_bytes()
    assert manifest["contract"]["inputs"]["output_folder"]["example"] == "~/Downloads/research_coscientist"
    assert manifest["metadata"]["init_config_review"]["fields"][4]["default"] == "~/Downloads/research_coscientist"
    assert {"status", "provenance_refs"} <= set(manifest["contract"]["outputs"]["primary"]["required_fields"])
    for path in (
        blueprint / "README.md",
        blueprint / "manifest.json",
        blueprint / "config" / "default.json",
        blueprint / "payloads" / "config" / "default.json",
        blueprint / "config" / "overwrite.json",
        blueprint / "scenario.json",
        blueprint / "payloads" / "runtime" / "runtime.py",
    ):
        assert "~/Download/research_coscientist" not in path.read_text(encoding="utf-8")


def test_manifest_uses_exactly_one_current_openshell_worker():
    manifest = _manifest()
    nodes = manifest["agents"]["nodes"]
    openshell = [
        node
        for node in nodes
        if (node.get("config") or {}).get("runner_module")
        == "MirrorNeuron.Runner.OpenShell"
    ]

    assert [node["node_id"] for node in openshell] == ["autonomous_research"]
    config = openshell[0]["config"]
    assert config["reuse_shared_sandbox"] is True
    assert config["persistent_workspace"] is True
    assert config["cleanup_remote_dir"] is False
    assert config["custom_openshell_image"] == "openshell_worker"
    assert config["policy"] == "openshell-policy.yaml"
    assert manifest["workflow"]["steps"][0]["label"].startswith("Deterministically")
    assert manifest["workflow"]["steps"][-1]["label"].startswith("Deterministically")


def test_runtime_payload_prefers_current_sandbox_output_over_stale_input(tmp_path, monkeypatch):
    runner = _runner()
    current = {
        "workflow_payload": {
            "evidence": {"source_refs": ["current"]},
            "recommendation": {"recommended_action": "review_research_packet"},
            "autonomous": {"isolation_required": True},
        }
    }
    stale = {"workflow_payload": {"goal": {"goal_id": "stale"}}}
    message = {
        "body": {
            "input": {"sandbox": {"stdout": json.dumps(stale)}},
            "sandbox": {"stdout": json.dumps(current)},
        }
    }
    message_path = tmp_path / "mirror_neuron_message.json"
    message_path.write_text(json.dumps(message), encoding="utf-8")
    monkeypatch.setenv("MN_MESSAGE_FILE", str(message_path))

    payload = runner._runtime_workflow_payload()

    assert payload["evidence"]["source_refs"] == ["current"]
    assert payload["autonomous"]["isolation_required"] is True
    assert "goal" not in payload


def test_autonomous_worker_can_request_skill_and_execute_generated_python(tmp_path):
    runner = _runner()

    class PlanningLlm:
        def generate_json(self, **_kwargs):
            return {
                "recommended_action": "review_research_packet",
                "confidence": "medium",
                "rationale": "Probe the candidate ledger before review.",
                "candidate_hypotheses": [
                    {
                        "statement": "Candidate A is distinguishable from baseline.",
                        "prediction": "The pre-specified measure changes.",
                        "evidence_support": ["local:note.md"],
                        "counterargument": "Ambient variation could explain it.",
                        "disconfirming_observation": "No controlled difference is observed.",
                    }
                ],
                "tool_requests": [{"tool": "knowledge_retrieve", "arguments": {"query": "controls"}}],
                "generated_python": "import json\npayload = json.loads(input())\nprint(json.dumps({'candidate_count': len(payload['candidate_hypotheses'])}))\n",
            }

    config = {
        "llm": {"mode": "live"},
        "agentic_research": {
            "allowed_tools": ["knowledge_retrieve", "hypothesis_rank", "generated_python", "finish"],
            "max_total_tool_calls": 3,
            "allow_generated_code": True,
            "generated_code": {"workspace": "generated", "timeout_seconds": 5},
        },
    }
    inputs = runner.normalize_inputs({"research_goal": "Compare candidates", "research_question": "Which survives controls?"})
    evidence = {"source_refs": ["local:note.md"], "evidence_gaps": [], "document_count": 1, "public_source_count": 0}
    posture = {"recommended_action": "review_research_packet", "confidence": "medium", "rationale": "Reviewable."}
    recommendation, autonomous, warnings = runner.run_autonomous_research(
        PlanningLlm(),
        inputs,
        evidence,
        {"context": "Use matched controls.", "citations": ["local:note.md"]},
        posture,
        config,
        [],
        [],
        workspace=tmp_path,
    )

    assert recommendation["candidate_hypotheses"]
    assert autonomous["session"]["tool_calls_used"] == 1
    assert autonomous["session"]["generated_code_runs"] == 1
    assert autonomous["generated_code_result"]["status"] == "completed"
    assert warnings == []
