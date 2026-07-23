from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mn_sdk import expand_manifest_source, is_manifest_source


ROOT = Path(__file__).resolve().parents[1]
SDK_ROOT = ROOT.parent / "mn-python-sdk"
SKILL_SOURCES = sorted((ROOT.parent / "mn-skills").glob("*/src"))
AGENT_SOURCES = sorted((ROOT.parent / "mn-agents").glob("*/src"))


def _run_handler_workflow(
    blueprint_id: str,
    tmp_path: Path,
    *,
    inputs: dict,
    config: dict,
) -> dict:
    blueprint = ROOT / blueprint_id
    payloads = blueprint / "payloads"
    scripts = payloads
    manifest = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    runtime_manifest = (
        expand_manifest_source(manifest, root_dir=blueprint)
        if is_manifest_source(manifest)
        else manifest
    )
    message_path = tmp_path / f"{blueprint_id}-message.json"
    message_path.write_text(json.dumps({"kwargs": inputs}), encoding="utf-8")
    result: dict = {}
    source_registry = manifest["agents"]["registry"]
    if is_manifest_source(manifest):
        assignments = []
        for node in runtime_manifest["agents"]["nodes"]:
            environment = (node.get("config") or {}).get("environment") or {}
            agent_id = environment.get("MN_WORKFLOW_AGENT_ID")
            if agent_id not in source_registry:
                continue
            assignments.append(
                {
                    "step_id": environment["MN_WORKFLOW_STEP_ID"],
                    "agent_id": agent_id,
                    "invocation_id": environment["MN_WORKFLOW_INVOCATION_ID"],
                    "needs": [],
                }
            )
    else:
        assignments = [
            {
                "step_id": step["id"],
                "agent_id": assignment["agent_id"],
                "invocation_id": f"{step['id']}__{assignment['agent_id']}",
                "needs": assignment.get("needs", []),
            }
            for step in manifest["workflow"]["steps"]
            for assignment in step["run"]["agents"]
        ]

    agent_outputs = {}
    executed_agents = []
    for assignment in assignments:
            step_id = assignment["step_id"]
            agent_id = assignment["agent_id"]
            invocation_id = assignment["invocation_id"]
            definition = source_registry[agent_id]
            message_path.write_text(
                json.dumps(
                    {
                        "body": {
                            "step_input": {"kwargs": inputs},
                            "agent_outputs": {
                                dependency: agent_outputs[dependency]
                                for dependency in assignment.get("needs", [])
                                if dependency in agent_outputs
                            },
                            "artifact_refs": [],
                        }
                    }
                ),
                encoding="utf-8",
            )
            environment = dict(os.environ)
            environment.update(
                {
                    "MN_JOB_ID": f"{blueprint_id}-handler-test",
                    "MN_MESSAGE_FILE": str(message_path),
                    "MN_RUN_ID": f"{blueprint_id}-handler-test",
                    "MN_RUN_DIR": str(tmp_path / "runs" / f"{blueprint_id}-handler-test"),
                    "MN_BLUEPRINT_BUNDLE_DIR": str(blueprint),
                    "MN_WORKFLOW_STEP_ID": step_id,
                    "MN_WORKFLOW_AGENT_ID": agent_id,
                    "MN_WORKFLOW_INVOCATION_ID": invocation_id,
                    "MN_WORKFLOW_IDEMPOTENCY_KEY": f"{blueprint_id}/{invocation_id}",
                    "MN_BLUEPRINT_CONFIG_JSON": json.dumps(config),
                    "MN_JOB_OUTPUT_DIR": str(tmp_path / "outputs"),
                    "MN_RUNS_ROOT": str(tmp_path / "runs"),
                    "MN_WORKDIR": str(tmp_path / "workspace"),
                    "PYTHONPATH": os.pathsep.join(
                        value
                        for value in (
                            str(SDK_ROOT),
                            *(str(path) for path in SKILL_SOURCES),
                            *(str(path) for path in AGENT_SOURCES),
                            environment.get("PYTHONPATH", ""),
                        )
                        if value
                    ),
                }
            )
            completed = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "mn_sdk.step_runtime",
                    "--handler",
                    definition["handler"],
                    "--with-json",
                    json.dumps(definition.get("with") or {}),
                ],
                cwd=scripts,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )
            assert completed.returncode == 0, completed.stderr
            result = json.loads(completed.stdout)
            assert result["workflow_step_id"] == step_id
            agent_outputs[agent_id] = dict(result.get("outputs") or {})
            executed_agents.append(agent_id)
    return {
        **dict(result.get("outputs") or {}),
        **{key: value for key, value in result.items() if key != "outputs"},
        "executed_agents": executed_agents,
        "run_dir": str(tmp_path / "runs" / f"{blueprint_id}-handler-test"),
    }


@pytest.mark.parametrize(
    ("blueprint_id", "inputs", "config"),
    [
        (
            "vc_assistant",
            {
                "document_folder": str(ROOT / "vc_assistant" / "examples" / "sample_inputs" / "aurora_ai"),
                "monitoring": {"max_cycles": 1},
            },
            {
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "agentic_research": {"enabled": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "purchase_research_assistant",
            {"input_folder": str(ROOT / "purchase_research_assistant" / "examples" / "sample_inputs")},
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "legal_assistant",
            {"document_folder": str(ROOT / "legal_assistant" / "examples" / "sample_inputs")},
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
            },
        ),
        (
            "financial_advisor",
            {"document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs")},
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
        (
            "research_coscientist",
            {"input_folder": str(ROOT / "research_coscientist" / "examples" / "sample_inputs")},
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "knowledge_rag": {"enabled": False, "required": False},
                "internet_research": {"enabled": False},
            },
        ),
    ],
)
def test_manifest_handlers_execute_as_message_chained_workflows(
    blueprint_id: str,
    inputs: dict,
    config: dict,
    tmp_path: Path,
):
    result = _run_handler_workflow(
        blueprint_id,
        tmp_path,
        inputs=inputs,
        config=config,
    )

    manifest = json.loads((ROOT / blueprint_id / "manifest.json").read_text())
    assert result["status"] == "completed"
    assert set(result["executed_agents"]) == set(manifest["agents"]["registry"])
    final_ref = result.get("final_artifact")
    assert isinstance(final_ref, dict)
    assert final_ref["kind"] == "final_artifact"
    assert (Path(result["run_dir"]) / final_ref["path"]).exists()
