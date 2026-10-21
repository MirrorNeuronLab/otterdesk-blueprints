from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk.manifest_converter import expand_manifest_source
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)


def blueprint_path(blueprint_id: str) -> Path:
    return ROOT / blueprint_id


def source_manifest(blueprint_id: str) -> dict[str, Any]:
    return blueprint_definition(
        read_blueprint(blueprint_path(blueprint_id) / "manifest.json")
    )


def expanded_manifest(blueprint_id: str) -> dict[str, Any]:
    return expand_manifest_source(
        source_manifest(blueprint_id), root_dir=blueprint_path(blueprint_id)
    )


def assert_modular_payload(blueprint_id: str) -> None:
    blueprint = blueprint_path(blueprint_id)
    manifest = source_manifest(blueprint_id)
    registry = (manifest.get("agents") or {}).get("registry") or {}
    logical_steps = [step["id"] for step in manifest["workflow"]["steps"]]

    assert set(logical_steps).isdisjoint(registry)
    assert not (blueprint / "payloads" / "domain" / "workflow.py").exists()
    assert not (blueprint / "payloads" / "domain" / "operations.py").exists()
    assert not (blueprint / "payloads" / "agents" / "domain.py").exists()

    runtime_path = blueprint / "payloads" / "runtime" / "runtime.py"
    if runtime_path.exists():
        runtime_source = runtime_path.read_text(encoding="utf-8")
        assert len(runtime_source.splitlines()) < 500
        assert "domain.runtime_services" in runtime_source
        assert "domain.intake" not in runtime_source
        assert "domain.reporting" not in runtime_source
        assert "agents." not in runtime_source
    else:
        assert not list((blueprint / "payloads/runtime").glob("*.py"))
        assert manifest.get("metadata", {}).get("mn_blocks") or (registry and all(
            spec.get("handler") == "mn_sdk.integrations.block_worker"
            and spec.get("with", {}).get("instance") for spec in registry.values()
        )), "A native SDK composition replaces runtime bindings."

    for step_path in (blueprint / "payloads" / "steps").glob("*.py"):
        tree = ast.parse(step_path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("domain")
            for node in ast.walk(tree)
        ), step_path

    for agent_id, spec in registry.items():
        if spec["handler"] == "mn_sdk.integrations.block_worker":
            from mn_blueprint_blocks import validate_instance
            instance = validate_instance(spec["with"]["instance"])
            assert spec["with"]["revision"] == f"{blueprint_id}@{read_blueprint(blueprint).manifest['version']}"
            assert instance.hooks["operation"].startswith("domain.")
        else:
            assert (blueprint / "payloads" / "agents" / f"{agent_id}.py").exists()
            assert spec["handler"] == f"agents.{agent_id}"


def _payload_pythonpath(blueprint_id: str) -> str:
    roots = [blueprint_path(blueprint_id) / "payloads", ROOT / "tests"]
    roots.extend(
        sorted(
            path
            for path in (blueprint_path(blueprint_id) / "payloads" / "skills").glob(
                "*/src"
            )
            if path.is_dir()
        )
    )
    roots.append(WORKSPACE / "mn-python-sdk")
    roots.extend(sorted((WORKSPACE / "mn-python-sdk" / "packages").glob("*/src")))
    roots.extend(sorted((WORKSPACE / "mn-skills").glob("*/src")))
    roots.extend(sorted((WORKSPACE / "mn-agents").glob("*/src")))
    existing = os.environ.get("PYTHONPATH")
    values = [str(path) for path in roots if path.exists()]
    if existing:
        values.append(existing)
    return os.pathsep.join(values)


def run_payload_script(blueprint_id: str, script: str) -> dict[str, Any]:
    env = dict(os.environ)
    env["PYTHONPATH"] = _payload_pythonpath(blueprint_id)
    completed = subprocess.run(
        [sys.executable, "-c", script],
        cwd=ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert completed.returncode == 0, completed.stderr
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    assert lines, completed.stderr
    return json.loads(lines[-1])


def assert_registry_handlers_import(blueprint_id: str) -> None:
    result = run_payload_script(
        blueprint_id,
        f"""
import importlib
import json
from pathlib import Path

from mn_sdk.blueprints import compile_blueprint, read_blueprint
manifest = compile_blueprint(read_blueprint(Path({str(blueprint_path(blueprint_id))!r}))).manifest
loaded = []
for node in manifest["agents"]["nodes"]:
    env = node.get("config", {{}}).get("environment", {{}})
    if not env.get("MN_WORKFLOW_STEP_HANDLER"):
        continue
    module = importlib.import_module(env["MN_WORKFLOW_STEP_HANDLER"])
    assert callable(module.run)
    parameters = json.loads(env.get("MN_WORKFLOW_STEP_WITH_JSON", "{{}}"))
    if module.__name__ == "mn_sdk.integrations.block_worker":
        instance = parameters.get("instance") or manifest["metadata"]["mn_blocks_lock"]["steps"][parameters["block_step_id"]]
        for reference in instance.get("hooks", {{}}).values():
            hook_module, function = reference.split(":")
            assert callable(getattr(importlib.import_module(hook_module), function))
    loaded.append(env["MN_WORKFLOW_AGENT_ID"])
print(json.dumps({{"loaded": loaded}}, sort_keys=True))
""",
    )
    expected = {node["config"]["environment"]["MN_WORKFLOW_AGENT_ID"]
                for node in expanded_manifest(blueprint_id)["agents"]["nodes"]
                if node.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER")}
    assert expected and set(result["loaded"]) == expected
