"""Catalog requirements accept their owning sources and enforce feature floors."""

from __future__ import annotations

import tomllib
from copy import deepcopy
from functools import lru_cache
from pathlib import Path

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.version_constraints import version_satisfies
from setuptools_scm import get_version

from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)
ROOTS = [ROOT]
PACKAGES = sorted(path.parent for path in ROOT.glob("*/manifest.json"))
CURRENT_FAMILY_BLUEPRINTS = {
    "financial_advisor",
    "research_assistant",
    "ros_amr_controller",
    "vc_assistant",
    "demo_context_memory_acl",
    "demo_context_compression",
}


def requires_current_family(root, name):
    if root.parent != ROOT and root.name not in CURRENT_FAMILY_BLUEPRINTS:
        return False
    if name == "mirrorneuron-python-sdk":
        return True
    if name == "mn-python-sdk-rag":
        # These two consumers use the independently supported lexical index.
        return root.name not in {"litigation_analyst", "software_architecture_advisor"}
    if name == "mirrorneuron-docs-to-markdown-skill":
        return root.name in {
            "financial_advisor",
            "vc_assistant",
            "procurement_manager",
            "research_assistant",
            "drug_discovery_research_assistant",
        }
    return name == "mn-python-sdk-mcp" and root.name in {"gtm_planner", "gtm_executor"}


@lru_cache
def workspace_distribution_versions():
    projects = [
        WORKSPACE / "mn-python-sdk",
        *sorted((WORKSPACE / "mn-python-sdk/packages").glob("*")),
        *sorted((WORKSPACE / "mn-skills").glob("*")),
        *sorted((WORKSPACE / "mn-agents").glob("*")),
        WORKSPACE / "Membrane/mn-context-engine-python-sdk",
        WORKSPACE / "Membrane/mn-context-source-code",
    ]
    versions = {}
    scm_versions = {}
    for project_root in projects:
        project_file = project_root / "pyproject.toml"
        if not project_file.is_file():
            continue
        metadata = tomllib.loads(project_file.read_text())
        project = metadata["project"]
        version = project.get("version")
        if version is None:
            scm = metadata["tool"]["setuptools_scm"]
            scm_root = (project_root / scm.get("root", ".")).resolve()
            if scm_root not in scm_versions:
                scm_versions[scm_root] = get_version(
                    root=str(scm_root), local_scheme="no-local-version"
                )
            version = scm_versions[scm_root]
        assert project["name"] not in versions, project_file
        versions[project["name"]] = version
    return versions


def test_blueprint_repositories_are_available():
    for root in ROOTS:
        assert (root / "index.json").is_file(), root
    assert PACKAGES


@pytest.mark.parametrize(
    "root", PACKAGES, ids=lambda root: f"{root.parent.name}/{root.name}"
)
def test_blueprint_dependencies_accept_owning_sources_and_required_contracts(root):
    package = read_blueprint(root)
    compiled = compile_blueprint(package).manifest
    for group in ("skill_dependencies", "agent_dependencies", "packages"):
        for dependency in compiled.get(group, []):
            if dependency.get("source") == "payload":
                project = tomllib.loads(
                    (
                        root / "payloads" / dependency["path"] / "pyproject.toml"
                    ).read_text()
                )["project"]
                assert project["name"] == dependency["name"]
                # Payload packages are shipped source, including unpublished
                # adapters; their own version must satisfy the authored range.
                assert version_satisfies(project["version"], dependency["version"])
            elif dependency["name"] == "mn-context-source-code":
                # The optional adapter has its own release series; it is a
                # reusable capability, not an SDK component/provider.
                assert group == "skill_dependencies"
                assert dependency["version"] == ">=0.1.3,<0.2"
                assert version_satisfies("0.1.3", dependency["version"])
                assert not version_satisfies("0.1.2", dependency["version"])
                assert not version_satisfies("0.2.0", dependency["version"])
            else:
                name, requirement = dependency["name"], dependency["version"]
                versions = workspace_distribution_versions()
                assert name in versions, (
                    root,
                    "missing owning source package",
                    dependency,
                )
                assert version_satisfies(versions[name], requirement), (
                    root,
                    dependency,
                    "rejects owning source version",
                    versions[name],
                )
                assert not version_satisfies("1.3.46", requirement), (root, dependency)
                if "mn.mcp" in package.manifest.get("extensions", {}) and (
                    name
                    in {
                        "mirrorneuron-python-sdk",
                        "mn-python-sdk-mcp",
                        "mn-python-sdk-job-response",
                    }
                ):
                    # Supervision/Skills have a newer coordinated SDK contract;
                    # domain skills and agent packages advance independently.
                    assert not version_satisfies("1.3.61.dev11", requirement), (
                        root,
                        dependency,
                    )
                    assert not version_satisfies("2.0.0", requirement), (
                        root,
                        dependency,
                    )
                elif requires_current_family(root, name):
                    assert not version_satisfies("1.3.57", requirement), (
                        root,
                        dependency,
                    )
                    assert not version_satisfies("2.0.0", requirement), (
                        root,
                        dependency,
                    )


def test_catalog_external_knowledge_profiles_match_the_installed_rag_provider(
    monkeypatch, tmp_path
):
    from mn_sdk_rag import RagConfig
    from mn_sdk.context_engine import blueprint_requires_context_engine

    monkeypatch.setenv("MN_JOB_ID", "catalog-rag-contract")
    monkeypatch.setenv("MN_JOB_DATA_DIR", str(tmp_path / "catalog-rag-contract"))
    checked = []
    for root in PACKAGES:
        package = read_blueprint(root)
        compiled = compile_blueprint(package)
        config = compiled.configuration.data
        if not config.get("knowledge_rag", {}).get("enabled"):
            continue
        profile = RagConfig.from_mapping(
            config["knowledge_rag"], blueprint_id=package.manifest["id"]
        )
        assert profile.backend == "duckdb", root
        assert Path(profile.db_path).suffix == ".duckdb", root
        for dependency in package.document("dependencies").get("packages", []):
            if dependency["name"] == "mn-python-sdk-rag":
                assert "milvus" not in dependency.get("extras", []), root
        if config.get("text_memory", {}).get("enabled") is False:
            if config.get("source_context", {}).get("enabled") is True:
                # Source intelligence still needs Membrane when runtime recall
                # is disabled. Turning both consumers off must release it.
                assert blueprint_requires_context_engine(
                    compiled.manifest, config, env={}
                ), root
                disabled = deepcopy(config)
                disabled["source_context"]["enabled"] = False
                assert not blueprint_requires_context_engine(
                    compiled.manifest, disabled, env={}
                ), root
            else:
                assert not blueprint_requires_context_engine(
                    compiled.manifest, config, env={}
                ), root
        checked.append(root)
    assert {root.name for root in checked} >= {
        "financial_advisor",
        "research_assistant",
        "vc_assistant",
    }
