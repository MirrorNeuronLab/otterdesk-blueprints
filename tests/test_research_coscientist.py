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


def _runner():
    path = ROOT / "research_coscientist" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
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
        ROOT / "research_coscientist" / "payloads" / "document_workflow" / "prompts"
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


def test_manifest_uses_exactly_one_current_openshell_worker():
    manifest = json.loads((ROOT / "research_coscientist" / "manifest.json").read_text(encoding="utf-8"))
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
    assert config["custom_openshell_image"] == "document_workflow/openshell_worker"
    assert config["policy"] == "document_workflow/openshell-policy.yaml"
    assert manifest["workflow"]["steps"][0]["label"].startswith("Deterministically")
    assert manifest["workflow"]["steps"][-1]["label"].startswith("Deterministically")


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
