"""The authoritative published inventory must prepare the v2 CPU profile."""

import ast
import json
from importlib.metadata import version
from pathlib import Path

import pytest
from packaging.specifiers import SpecifierSet
from packaging.requirements import Requirement
from mn_sdk.blueprints import (
    blueprint_definition,
    compile_blueprint,
    read_blueprint,
    resolve_config,
)
from mn_sdk.context_engine import blueprint_requires_context_engine

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
ACTIVE = {"cctv_operator", "software_architecture_advisor", "litigation_analyst", "vc_assistant", "mac_security_investigator"}
SOURCE_ACTIVE = {"drug_discovery_research_assistant"}


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
        name in ACTIVE | SOURCE_ACTIVE
    )
    disabled = resolve_config(package, {"text_memory": {"enabled": False}, "source_context": {"enabled": False}}).data
    assert not blueprint_requires_context_engine(compiled, disabled, env={})
    dependencies = package.document("dependencies")["packages"]
    extras = [r for r in dependencies if r["name"] == "mirrorneuron-python-sdk"]
    assert len(extras) == 1
    supported = SpecifierSet(extras[0]["version"])
    assert supported.contains(version("mirrorneuron-python-sdk"))
    assert not supported.contains("1.3.57")
    assert not supported.contains("2.0")
    assert extras[0].get("extras", []) == (["context"] if name in ACTIVE | SOURCE_ACTIVE else [])


def test_all_catalog_context_consumers_resolve_the_v2_sdk_and_wire_protocol():
    import tomllib
    from mn_sdk import context_pb2
    from mn_sdk.context_engine_readiness import PROTOCOL
    import mn_sdk
    from mn_context_engine_sdk.proto import context_pb2 as engine

    project = tomllib.loads((Path(mn_sdk.__file__).parents[1] / "pyproject.toml").read_text())
    dependency, = [Requirement(value) for value in project["project"]["optional-dependencies"]["context"]
                   if Requirement(value).name == "mirrorneuron-membrane-python-sdk"]
    assert dependency.extras == {"grpc"}
    assert dependency.specifier.contains("2.1.0")
    assert not dependency.specifier.contains("1.3.57")
    assert not dependency.specifier.contains("2.0.0")
    assert not dependency.specifier.contains("3.0.0")
    assert context_pb2.DESCRIPTOR.package == PROTOCOL == "mirrorneuron.context.v2"
    assert context_pb2.DESCRIPTOR.serialized_pb == engine.DESCRIPTOR.serialized_pb
    assert set(context_pb2.DESCRIPTOR.services_by_name["ContextEngine"].methods_by_name) == {
        "TextMemory", "CompileEvidence", "CompilePrompt"
    }


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
