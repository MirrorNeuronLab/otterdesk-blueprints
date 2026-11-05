"""Local catalog inventory and deterministic worker activity boundary tests."""

import ast
import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint

ROOT = Path(__file__).resolve().parents[1]
CATALOGS = [ROOT]
BLUEPRINTS = [
    (root, name)
    for root in CATALOGS
    if (root / "index.json").exists()
    for name in json.loads((root / "index.json").read_text())
]


@pytest.mark.parametrize(
    "root,name", BLUEPRINTS, ids=[f"{root.name}/{name}" for root, name in BLUEPRINTS]
)
def test_catalog_has_activity_or_shared_workflow_progress_without_local_publishers(
    root, name
):
    files = list((root / name / "payloads").rglob("*.py"))
    texts = [path.read_text() for path in files]
    for path, text in zip(files, texts):
        ast.parse(text, filename=str(path))
    has_domain_activity = any(
        "activity_operation" in text
        or "report_activity" in text
        or '"message":' in text
        or '"summary":' in text
        for text in texts
    )
    if not has_domain_activity:
        # Native-computation products use stock block workers. Their shared
        # Core step boundaries own progress; domain hooks need no publisher.
        compiled = compile_blueprint(read_blueprint(root / name)).manifest
        nodes = {node["node_id"]: node for node in compiled["agents"]["nodes"]}
        steps = compiled.get("workflow", {}).get("steps", [])
        assert steps, f"{name}: no domain activity or shared workflow progress"
        for step in steps:
            assert step.get("label") and step.get("goal") and step.get("emits")
            assert nodes[step["start_agent_id"]]["agent_type"] == "step_source"
            assert nodes[step["end_agent_id"]]["agent_type"] == "step_sink"
            workers = [
                nodes[identity]
                for identity in step["agent_ids"]
                if identity not in {step["start_agent_id"], step["end_agent_id"]}
            ]
            assert workers
            for worker in workers:
                config = worker["config"]
                assert config["command"][-2:] == ["-m", "mn_sdk.step_runtime"]
                assert (
                    config["environment"]["MN_WORKFLOW_STEP_HANDLER"]
                    == "mn_sdk.integrations.block_worker"
                )
                assert config["environment"]["MN_WORKFLOW_STEP_ID"] == step["id"]
    # New activity transport belongs to the SDK rather than domain packages.
    for path, text in zip(files, texts):
        if "activity_operation" in text or "report_activity" in text:
            tree = ast.parse(text)
            assert not any(
                isinstance(node, ast.FunctionDef)
                and node.name
                in {"report_activity", "activity_operation", "normalize_runtime_event"}
                for node in tree.body
            )
