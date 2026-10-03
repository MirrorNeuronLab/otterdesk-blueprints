"""The authoritative published inventory must prepare the v2 CPU profile."""

import ast
import json
from pathlib import Path

import pytest
from mn_sdk.blueprints import (
    blueprint_definition,
    compile_blueprint,
    read_blueprint,
    resolve_config,
)
from mn_sdk.context_engine import blueprint_requires_context_engine

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
ACTIVE = {"cctv_operator", "software_architecture_advisor", "litigation_analyst", "vc_assistant"}


@pytest.mark.parametrize("name", CATALOG)
def test_context_contract_and_effective_disabled_override(name):
    package = read_blueprint(ROOT / name)
    config = resolve_config(package).data
    definition = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    assert (
        package.extension("mn.context")["text_memory"]["contract"]
        == "mn.context.text.v1"
    )
    assert "memory_layer" not in config and "memory_layer" not in definition["metadata"]
    assert config["text_memory"]["enabled"] == (name in ACTIVE)
    assert blueprint_requires_context_engine(compiled, config, env={}) == (
        name in ACTIVE
    )
    disabled = resolve_config(package, {"text_memory": {"enabled": False}}).data
    assert not blueprint_requires_context_engine(compiled, disabled, env={})
    dependencies = package.document("dependencies")["packages"]
    extras = [r for r in dependencies if r["name"] == "mirrorneuron-python-sdk"]
    assert len(extras) == 1 and extras[0]["version"] == ">=1.3.58.dev0,<2"
    assert extras[0].get("extras", []) == (["context"] if name in ACTIVE else [])


@pytest.mark.parametrize("name", CATALOG)
def test_published_sources_have_no_retired_memory_imports_or_settings(name):
    root = ROOT / name
    retired = {"FileMemory", "WorkingMemory", "MemoryItem", "runtime_file_memory"}
    for path in (root / "payloads").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                assert node.module != "mn_sdk.file_memory", path
                assert not retired.intersection(alias.name for alias in node.names), (
                    path
                )
    for path in [
        root / "config/default.json",
        root / "execution.json",
        root / "extensions/context.json",
    ]:
        text = path.read_text()
        for key in (
            "memory_layer",
            "working_memory_persist_to_redis",
            "use_model_compression",
        ):
            assert f'"{key}"' not in text, path
    for path in root.rglob("Dockerfile"):
        assert not any(
            symbol in path.read_text()
            for symbol in ("MemoryItem", "WorkingMemory", "FileMemory")
        ), path
