"""RAG contracts for the current catalog, without historical sibling fixtures."""
import json
import ast
from pathlib import Path

import pytest
from mn_sdk.blueprints import read_blueprint, blueprint_definition, resolve_config
from mn_sdk_rag import RagConfig, RagError

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
RAG = [name for name in CATALOG if (ROOT / name / "extensions/rag.json").exists()
       and json.loads((ROOT / name / "extensions/rag.json").read_text()).get("enabled", True)]


@pytest.mark.parametrize("name", RAG)
def test_current_catalog_uses_base_duckdb_rag_and_explicit_knowledge(name, tmp_path):
    package = read_blueprint(ROOT / name)
    manifest = blueprint_definition(package)
    rag = json.loads((ROOT / name / "extensions/rag.json").read_text())
    # The public SDK owns the default when a package omits this optional field.
    resolved_rag = RagConfig.from_mapping({**rag, "db_root": str(tmp_path)}, blueprint_id=name)
    assert resolved_rag.backend == "duckdb"
    assert "redis_url" not in rag
    config = resolve_config(package).data
    assert RagConfig.from_mapping(
        {**config["knowledge_rag"], "db_root": str(tmp_path)}, blueprint_id=name
    ).backend == "duckdb"
    dependencies = json.loads((ROOT / name / "dependencies.json").read_text())["packages"]
    assert "mirrorneuron-python-sdk" in {p["name"] for p in dependencies}
    for declaration in dependencies:
        assert "milvus" not in declaration.get("extras", [])
    resources = manifest["metadata"]["job_data"]["resources"]
    knowledge = next(r for r in resources if r["name"] == "knowledge")
    assert knowledge["path"] == "knowledge"
    assert any(r["path"] == "databases/rag" for r in resources)


@pytest.mark.parametrize("name", RAG)
def test_payload_rag_consumers_declare_the_worker_dependency(name):
    # Enabling platform-owned Job knowledge (for example CT explanations)
    # does not install a second RAG engine inside the workflow worker.
    imports = [
        node
        for path in (ROOT / name / "payloads").rglob("*.py")
        for node in ast.walk(ast.parse(path.read_text()))
        if isinstance(node, (ast.Import, ast.ImportFrom))
    ]
    uses_rag = any(
        isinstance(node, ast.ImportFrom) and (node.module or "").startswith("mn_sdk_rag")
        or isinstance(node, ast.Import) and any(alias.name.startswith("mn_sdk_rag") for alias in node.names)
        for node in imports
    )
    if uses_rag:
        dependencies = read_blueprint(ROOT / name).document("dependencies")["packages"]
        assert "mn-python-sdk-rag" in {p["name"] for p in dependencies}


@pytest.mark.parametrize("backend", ["redis_vector_rag", "milvus", "lexical_plain_text"])
def test_public_rag_config_rejects_retired_backends(backend, tmp_path):
    with pytest.raises(RagError, match="Unsupported RAG backend"):
        RagConfig.from_mapping({"backend": backend, "db_root": str(tmp_path)})


def test_vc_worker_installs_duckdb_through_rag_dependency():
    requirements = (ROOT / "vc_assistant/payloads/requirements.txt").read_text()
    dockerfile = (ROOT / "vc_assistant/payloads/docker_worker/Dockerfile").read_text()
    assert "pymilvus" not in requirements and "[milvus]" not in requirements
    assert "python3 -c 'import duckdb'" in dockerfile


def test_mac_private_evidence_has_explicitly_disabled_product_rag():
    package = read_blueprint(ROOT / "mac_security_investigator")
    assert package.extension("mn.rag")["enabled"] is False
    assert blueprint_definition(package)["knowledge_rag"]["enabled"] is False
    assert "mn-python-sdk-rag" not in {r["name"] for r in package.document("dependencies")["packages"]}
