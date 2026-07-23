from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from mn_sdk.manifest_converter import expand_manifest_source


ROOT = Path(__file__).resolve().parents[1]


def source_manifest(blueprint_id: str) -> dict[str, Any]:
    return json.loads((ROOT / blueprint_id / "manifest.json").read_text(encoding="utf-8"))


def expanded_manifest(blueprint_id: str) -> dict[str, Any]:
    return expand_manifest_source(source_manifest(blueprint_id), root_dir=ROOT / blueprint_id)


def assert_modular_payload(blueprint_id: str) -> None:
    blueprint = ROOT / blueprint_id
    manifest = source_manifest(blueprint_id)
    registry = (manifest.get("agents") or {}).get("registry") or {}
    logical_steps = [step["id"] for step in manifest["workflow"]["steps"]]

    assert set(logical_steps).isdisjoint(registry)
    assert not (blueprint / "payloads" / "domain" / "workflow.py").exists()
    assert not (blueprint / "payloads" / "domain" / "operations.py").exists()
    assert not (blueprint / "payloads" / "agents" / "domain.py").exists()

    runtime_path = blueprint / "payloads" / "runtime" / "runtime.py"
    runtime_source = runtime_path.read_text(encoding="utf-8")
    assert len(runtime_source.splitlines()) < 500
    assert "domain.runtime_services" in runtime_source
    assert "domain.intake" not in runtime_source
    assert "domain.reporting" not in runtime_source
    assert "agents." not in runtime_source

    for step_path in (blueprint / "payloads" / "steps").glob("*.py"):
        tree = ast.parse(step_path.read_text(encoding="utf-8"))
        assert not any(
            isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("domain")
            for node in ast.walk(tree)
        ), step_path

    for agent_id, spec in registry.items():
        assert (blueprint / "payloads" / "agents" / f"{agent_id}.py").exists()
        assert spec["handler"] == f"agents.{agent_id}"


def _payload_pythonpath(blueprint_id: str) -> str:
    roots = [ROOT / blueprint_id / "payloads"]
    roots.extend(sorted((ROOT.parent / "mn-skills").glob("*/src")))
    roots.extend(sorted((ROOT.parent / "mn-agents").glob("*/src")))
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
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
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

manifest = json.loads(Path({str(ROOT / blueprint_id / 'manifest.json')!r}).read_text())
registry = (manifest.get("agents") or {{}}).get("registry") or {{}}
loaded = []
for agent_id, spec in registry.items():
    module = importlib.import_module(spec["handler"])
    assert callable(module.run)
    loaded.append(agent_id)
print(json.dumps({{"loaded": loaded}}, sort_keys=True))
""",
    )
    assert set(result["loaded"]) == set((source_manifest(blueprint_id)["agents"]["registry"]))
