"""Catalog-wide checks for the shared SDK package installation contract."""

from __future__ import annotations

import ast
import copy
import importlib
import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint
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
                assert record["name"].startswith("mn-python-sdk-")
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
    assert requirements, blueprint_id
    for component in component_requirements(prepared):
        if local:
            assert component.requirement not in requirements
            assert "/tmp/mn-skill-runtime/local/" + component.name in local_requirements
        else:
            assert component.requirement in requirements
    if not local:
        assert not local_requirements
    if blueprint_id == "software_architecture_advisor":
        if local:
            assert "software_architecture_graph_skill" in local_requirements
            assert "mn-software-architecture-graph-skill==" not in requirements
        else:
            assert "mn-software-architecture-graph-skill==1.3.22" in requirements
            assert not any(
                "local-requirements.txt" in value.decode()
                for key, value in payloads.items()
                if key.endswith("Dockerfile")
            )
