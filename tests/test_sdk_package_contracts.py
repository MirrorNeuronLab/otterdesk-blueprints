"""Catalog-wide checks for the shared SDK package installation contract."""

from __future__ import annotations

import ast
import copy
import importlib
import json
from pathlib import Path

import pytest

from mn_sdk.version_constraints import dependency_requirement
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config
from mn_sdk.context_engine import blueprint_requires_context_engine
from mn_sdk.components.dependencies import component_requirements
from mn_sdk.components.installation import SDKInstallation
from mn_sdk.submission_preparation import (
    prepare_manifest_for_submission,
    stage_skill_dependency_payloads_for_manifest,
    stage_skill_runtime_support_payloads_for_manifest,
)

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINTS = json.loads((ROOT / "index.json").read_text())


@pytest.mark.parametrize("blueprint_id", BLUEPRINTS)
def test_catalog_dependencies_use_gar_packages_and_keep_domain_skills(blueprint_id):
    root = ROOT / blueprint_id
    dependencies = json.loads((root / "dependencies.json").read_text())
    assert "packages" in dependencies
    assert dependencies["packages"]
    for group in ("packages", "skills"):
        for record in dependencies[group]:
            assert record["type"] == "pip" and record["source"] == "gar"
            assert record["version"]
            assert not {"path", "format"} & record.keys()
            if group == "packages":
                assert record["name"].startswith("mn-python-sdk-") or record["name"] == "mirrorneuron-python-sdk"
            else:
                assert not record["name"].startswith("mn-python-sdk-")
    compiled = compile_blueprint(read_blueprint(root)).manifest
    assert compiled["packages"] == dependencies["packages"]
    assert component_requirements(compiled)
    if blueprint_id == "gtm_assistant":
        assert "mirrorneuron-email-delivery-skill" in {
            r["name"] for r in dependencies["skills"]
        }


@pytest.mark.parametrize("blueprint_id", BLUEPRINTS)
def test_payload_sdk_imports_resolve_and_have_no_package_bootstrap(blueprint_id):
    for path in (ROOT / blueprint_id / "payloads").rglob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                assert node.name != "_bootstrap_runtime", path
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith(("mn_sdk.", "mn_sdk_", "mn_prototype_")):
                    module = importlib.import_module(node.module)
                    for symbol in node.names:
                        if symbol.name != "*":
                            assert hasattr(module, symbol.name), (
                                path,
                                node.module,
                                symbol.name,
                            )
                assert not node.module.startswith("mn_blueprint_support"), path


@pytest.mark.parametrize("local", [True, False], ids=["source", "binary"])
@pytest.mark.parametrize("blueprint_id", BLUEPRINTS)
def test_catalog_preparation_stages_the_correct_dependency_mode(
    blueprint_id, local, monkeypatch
):
    from mn_sdk import submission_preparation
    from mn_sdk.components import installation

    root = ROOT / blueprint_id
    sdk_root = Path(submission_preparation.__file__).resolve().parents[1]
    monkeypatch.setenv("MN_USE_LOCAL_SKILLS", "1" if local else "0")
    monkeypatch.setattr(
        installation,
        "sdk_installation",
        lambda: (
            SDKInstallation("local", source_root=sdk_root)
            if local
            else SDKInstallation("wheel")
        ),
    )
    monkeypatch.setattr(
        submission_preparation,
        "ensure_runtime_modules_for_manifest",
        lambda *args, **kwargs: {},
    )
    declaration = blueprint_definition(read_blueprint(root))
    before = copy.deepcopy(declaration)
    needs_context = blueprint_requires_context_engine(before, resolve_config(read_blueprint(root)).data, env={})
    prepared = prepare_manifest_for_submission(root, declaration)
    assert declaration == before
    assert prepared["packages"] == before["packages"]
    payloads = {}
    stage_skill_runtime_support_payloads_for_manifest(
        prepared, payloads, bundle_dir=root
    )
    stage_skill_dependency_payloads_for_manifest(prepared, payloads, bundle_dir=root)
    requirements = "\n".join(
        value.decode()
        for key, value in payloads.items()
        if key.endswith("requirements.txt")
        and not key.endswith("local-requirements.txt")
    )
    local_requirements = "\n".join(
        value.decode()
        for key, value in payloads.items()
        if key.endswith("local-requirements.txt")
    )
    if blueprint_id in {"vc_assistant", "financial_advisor", "procurement_manager", "research_assistant", "litigation_analyst"}:
        retired = {"mirrorneuron-document-reading-skill", "mirrorneuron-llm-ocr-skill", "mirrorneuron-pdf-extract-skill"}
        assert all(name not in requirements for name in retired)
        assert not retired & {
            record["name"] for record in before["skill_dependencies"]
        }
        if local:
            assert "/tmp/mn-skill-runtime/local/docs_to_markdown_skill" in local_requirements
        else:
            assert "mirrorneuron-docs-to-markdown-skill>=1.3.58.dev0,<2" in requirements
    python_workers = [n for n in prepared.get('agents', {}).get('nodes', [])
                      if n.get('config', {}).get('runner_module') in {'MirrorNeuron.Runner.DockerWorker', 'MirrorNeuron.Runner.HostLocal'}]
    if not requirements:
        # Compose-only and supervised services prepare their Python environment
        # on the native host rather than through a Docker build context.
        assert blueprint_id in {'ros_amr_controller', 'gtm_planner', 'gtm_executor', 'mac_security_investigator'}
        assert not any(n.get('config', {}).get('runner_module') == 'MirrorNeuron.Runner.DockerWorker' for n in python_workers)
        if local:
            sources = prepared['metadata']['mn_local_skill_dependencies']['sources']
            assert any(r['package'] == 'mirrorneuron-python-sdk' for r in sources)
            assert all(any(r['package'] == component.distribution for r in sources)
                       for component in component_requirements(prepared))
            if needs_context:
                assert any(r['package'] == 'mirrorneuron-membrane-python-sdk'
                           and r['extras'] == '[grpc]' for r in sources)
        else:
            assert not prepared.get('metadata', {}).get('mn_local_skill_dependencies')
        return
    for component in component_requirements(prepared):
        if local:
            assert component.requirement not in requirements
            assert "/tmp/mn-skill-runtime/local/" + component.name in local_requirements
        else:
            assert component.requirement in requirements
    if not local:
        assert not local_requirements
    if not local:
        declared_sdk = next(row for row in before["packages"]
                            if row["name"] == "mirrorneuron-python-sdk")
        sdk_name = declared_sdk["name"]
        if declared_sdk.get("extras"):
            sdk_name += "[" + ",".join(sorted(declared_sdk["extras"])) + "]"
        assert dependency_requirement(sdk_name, declared_sdk["version"]) in requirements
    if needs_context:
        if local:
            assert '/mn-context-engine-python-sdk[grpc]' in local_requirements
            assert '/mn-python-sdk[context]' in local_requirements
            assert any(key.endswith('/mn_context_engine_sdk/text_memory.py') for key in payloads)
            assert any(key.endswith('/mn_context_engine_sdk/proto/context_pb2.py')
                       and b'mirrorneuron.context.v2' in value for key, value in payloads.items())
        else:
            sdk = next(row for row in before['packages'] if row['name'] == 'mirrorneuron-python-sdk')
            assert dependency_requirement('mirrorneuron-python-sdk[context]', sdk['version']) in requirements
    if blueprint_id == "software_architecture_advisor":
        if local:
            assert "graph_analysis_skill" in local_requirements
            assert "mirrorneuron-graph-analysis-skill==" not in requirements
        else:
            from packaging.requirements import Requirement
            declared_graph = Requirement(dependency_requirement('mirrorneuron-graph-analysis-skill',
                next(row['version'] for row in before['skill_dependencies']
                     if row['name'] == 'mirrorneuron-graph-analysis-skill')))
            graph = next(Requirement(line) for line in requirements.splitlines()
                         if line.startswith('mirrorneuron-graph-analysis-skill'))
            assert graph.name == declared_graph.name
            if graph.url:
                from urllib.parse import unquote, urlsplit
                from packaging.utils import parse_wheel_filename
                distribution, version, _, _ = parse_wheel_filename(
                    Path(unquote(urlsplit(graph.url).path)).name)
                assert distribution == graph.name
                assert declared_graph.specifier.contains(version)
            else:
                assert graph.specifier == declared_graph.specifier
            assert not any(
                "local-requirements.txt" in value.decode()
                for key, value in payloads.items()
                if key.endswith("Dockerfile")
            )
