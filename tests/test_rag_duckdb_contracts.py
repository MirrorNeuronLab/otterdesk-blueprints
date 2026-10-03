"""RAG contracts for the current catalog, without historical sibling fixtures."""
import json
from pathlib import Path

import pytest
from mn_sdk.blueprints import read_blueprint, blueprint_definition, resolve_config

ROOT = Path(__file__).resolve().parents[1]
CATALOG = json.loads((ROOT / "index.json").read_text())
RAG = [name for name in CATALOG if (ROOT / name / "extensions/rag.json").exists()]


@pytest.mark.parametrize("name", RAG)
def test_current_catalog_uses_base_duckdb_rag_and_explicit_knowledge(name):
    package = read_blueprint(ROOT / name)
    manifest = blueprint_definition(package)
    rag = json.loads((ROOT / name / "extensions/rag.json").read_text())
    assert rag["backend"] == "duckdb"
    assert "redis_url" not in rag
    config = resolve_config(package).data
    assert config.get("knowledge_rag", {}).get("backend", "duckdb") == "duckdb"
    dependencies = json.loads((ROOT / name / "dependencies.json").read_text())["packages"]
    declaration = next(p for p in dependencies if p["name"] == "mn-python-sdk-rag")
    assert "milvus" not in declaration.get("extras", [])
    resources = manifest["metadata"]["job_data"]["resources"]
    knowledge = next(r for r in resources if r["name"] == "knowledge")
    assert knowledge["path"] == "knowledge"
    assert any(r["path"] == "databases/rag" for r in resources)


def test_vc_worker_installs_duckdb_through_rag_dependency():
    requirements = (ROOT / "vc_assistant/payloads/requirements.txt").read_text()
    dockerfile = (ROOT / "vc_assistant/payloads/docker_worker/Dockerfile").read_text()
    assert "pymilvus" not in requirements and "[milvus]" not in requirements
    assert "python3 -c 'import duckdb'" in dockerfile
