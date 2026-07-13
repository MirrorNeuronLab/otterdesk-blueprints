from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORT_SRC = ROOT.parent / "mn-skills" / "blueprint_support_skill" / "src"
SDK_SRC = ROOT.parent / "mn-python-sdk"
for path in (SDK_SRC, SUPPORT_SRC):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))


def _runner():
    path = ROOT / "multi_agent_research_coscientist" / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
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
        ROOT / "multi_agent_research_coscientist" / "payloads" / "document_workflow" / "prompts"
    )
    assert "Research Packet System Prompt" in runner.load_prompt("research-packet-system.md")
    assert "Multi-Agent Research Review Task" in runner.load_prompt("research-review-task.md")

    output = tmp_path / "outputs"
    result = runner.run_blueprint(
        inputs={
            "research_goal": "Evaluate a low-risk cooling-loop efficiency hypothesis.",
            "research_domain": "engineering",
            "research_question": "What measurement distinguishes the hypothesis from ambient variation?",
            "scope": "Desk research only.",
            "input_folder": str(ROOT / "multi_agent_research_coscientist" / "examples" / "sample_inputs"),
            "output_folder": str(output),
        },
        config={"llm": {"mode": "fake"}},
        runs_root=tmp_path / "runs",
        run_id="research-coscientist-test",
    )

    packet = result["final_artifact"]
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
