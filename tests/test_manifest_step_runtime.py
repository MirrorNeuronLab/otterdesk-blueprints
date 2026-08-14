from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from mn_sdk import expand_manifest_source, is_manifest_source

from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
SDK_ROOT = WORKSPACE / "mn-python-sdk"
SKILL_SOURCES = sorted((WORKSPACE / "mn-skills").glob("*/src"))
AGENT_SOURCES = sorted((WORKSPACE / "mn-agents").glob("*/src"))


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
        (
            "growth_partnerships_coworker",
            {
                "input_folder": str(ROOT / "growth_partnerships_coworker" / "examples" / "sample_inputs"),
                "contacts_csv": str(ROOT / "growth_partnerships_coworker" / "examples" / "sample_inputs" / "edtech_contacts_sample.csv"),
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
                "gtm": {"max_contacts_per_run": 5, "outreach_mode": "draft_only"},
            },
        ),
        (
            "business_finance_coworker",
            {
                "input_folder": str(ROOT / "business_finance_coworker" / "examples" / "sample_inputs"),
                "metrics_file": str(ROOT / "business_finance_coworker" / "examples" / "sample_inputs" / "business_metrics.json"),
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
            },
        ),
        (
            "learning_quality_safety_coworker",
            {
                "input_folder": str(ROOT / "learning_quality_safety_coworker" / "examples" / "sample_inputs"),
                "content_backlog_file": str(ROOT / "learning_quality_safety_coworker" / "examples" / "sample_inputs" / "content_backlog.json"),
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
            },
        ),
        (
            "content_studio_coworker",
            {
                "input_folder": str(ROOT / "content_studio_coworker" / "examples" / "sample_inputs"),
                "learning_briefs_file": str(ROOT / "content_studio_coworker" / "examples" / "sample_inputs" / "approved_learning_briefs.json"),
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
            },
        ),
        (
            "gtm_assistant",
            {
                "input_folder": str(ROOT / "gtm_assistant" / "examples" / "sample_inputs"),
                "customer_feedback_file": str(ROOT / "gtm_assistant" / "examples" / "sample_inputs" / "parent_feedback.csv"),
                "business_goal": "Build a successful business for Bibblio.",
                "goal_id": "bibblio-business-success",
            },
            {
                "execution": {"quick_test": True},
                "llm": {"mode": "fake", "require_live": False},
                "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
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
    final_path = Path(result["run_dir"]) / final_ref["path"]
    assert final_path.exists()
    if manifest["metadata"].get("collaboration_group") == "business-success-team":
        final_artifact = json.loads(final_path.read_text(encoding="utf-8"))
        assert final_artifact["schema_version"] == "mn.business_success.role_brief.v1"
        assert final_artifact["type"] == manifest["contracts"]["outputs"]["artifacts"][1]["type"]
        assert final_artifact["business_name"] == "Bibblio"
        assert final_artifact["business_goal"] == "Build a successful business for Bibblio."
        assert final_artifact["planning_horizon_days"] == 90
        assert final_artifact["role_contribution"]
        assert final_artifact["north_star_question"]
        assert len(final_artifact["role_scorecard"]) >= 4
        assert len(final_artifact["founder_decisions"]) >= 3
        assert len(final_artifact["ninety_day_plan"]) == 3
        assert len(final_artifact["cross_functional_handoffs"]) == 4
        assert final_artifact["collaboration"]["peer_input_mode"] == "explicit_mcp_servers_only"
        assert "team_synthesis" in final_artifact["collaboration"]
        assert len(final_artifact["collaboration"]["team_synthesis"]["unresolved_without_peer_evidence"]) == 4
        if blueprint_id == "gtm_assistant":
            delivery = final_artifact["evidence"]["development_email_delivery"]
            assert delivery["status"] == "not_sent"
            assert delivery["recipient_count"] == 0
            assert delivery["customer_addresses_used"] is False
            assert delivery["customer_specific_data_used"] is False


def test_generic_business_identity_replaces_the_default_demo_context(tmp_path: Path):
    blueprint_id = "business_finance_coworker"
    result = _run_handler_workflow(
        blueprint_id,
        tmp_path,
        inputs={
            "business_name": "Northstar Learning",
            "business_goal": "Reach sustainable product-market fit for Northstar Learning.",
            "goal_id": "northstar-sustainable-fit",
            "planning_horizon_days": 120,
            "input_folder": str(ROOT / blueprint_id / "examples" / "sample_inputs"),
            "metrics_file": str(ROOT / blueprint_id / "examples" / "sample_inputs" / "business_metrics.json"),
        },
        config={
            "execution": {"quick_test": True},
            "llm": {"mode": "fake", "require_live": False},
            "mcp_collaboration": {"publish_local_exchange": True, "peer_reads_enabled": False},
        },
    )
    final_path = Path(result["run_dir"]) / result["final_artifact"]["path"]
    final_artifact = json.loads(final_path.read_text(encoding="utf-8"))
    assert final_artifact["business_name"] == "Northstar Learning"
    assert final_artifact["business_goal"] == "Reach sustainable product-market fit for Northstar Learning."
    assert final_artifact["goal_id"] == "northstar-sustainable-fit"
    assert final_artifact["planning_horizon_days"] == 120
    assert "Bibblio" not in json.dumps(final_artifact)
