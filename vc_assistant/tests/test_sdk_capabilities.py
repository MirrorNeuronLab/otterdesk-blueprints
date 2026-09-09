"""The VC bundle consumes current SDK capabilities without retired skill shims."""

import ast
import json
from pathlib import Path

from mn_sdk import expand_manifest_source
from mn_sdk.blueprints import blueprint_definition, read_blueprint
from mn_sdk.components import component_requirement_lines

ROOT = Path(__file__).resolve().parents[1]


def test_compiled_dependencies_enable_only_required_sdk_capabilities():
    source = blueprint_definition(read_blueprint(ROOT))
    compiled = expand_manifest_source(source, root_dir=ROOT)
    expected = {
        "mn-python-sdk-common==0.1.0",
        "mn-python-sdk-models==0.1.0",
        "mn-python-sdk-rag[milvus]==0.1.0",
        "mn-python-sdk-job-response==0.1.0",
        "mn-python-sdk-mcp==0.1.0",
    }
    assert set(component_requirement_lines(source)) == expected
    assert set(component_requirement_lines(compiled)) == expected
    assert compiled["packages"] == source["packages"]
    retired = {
        "mirrorneuron-blueprint-support-skill",
        "mirrorneuron-rag-skill",
        "mirrorneuron-job-response-skill",
        "mirrorneuron-mcp-client-skill",
    }
    assert not retired.intersection(d["name"] for d in source["skill_dependencies"])
    config = json.loads((ROOT / "config/default.json").read_text())
    for capability in ("llm_ocr", "web_browser"):
        assert "package" not in config["input_skills"][capability]


def test_payload_has_no_retired_infrastructure_imports():
    retired = {"mn_blueprint_support", "mn_rag_skill", "mn_job_response_skill", "mn_mcp_client_skill"}
    for path in (ROOT / "payloads").rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            else:
                continue
            assert not retired.intersection(name.split(".")[0] for name in names), path


def test_rag_preparation_injects_sdk_model_gateway(monkeypatch):
    from domain import knowledge
    import mn_sdk_rag
    from mn_sdk.integrations.rag import build_runtime_embedder

    captured = {}

    def prepare(**options):
        captured.update(options)
        return {"enabled": True, "status": "ready"}

    monkeypatch.setattr(mn_sdk_rag, "prepare_blueprint_knowledge_rag", prepare)
    monkeypatch.setattr(knowledge, "fake_llm_mode_enabled", lambda *_: False)
    monkeypatch.setattr(knowledge, "fake_skills_mode_enabled", lambda *_: False)
    monkeypatch.setattr(knowledge, "quick_test_mode_enabled", lambda *_: False)
    result = knowledge.prepare_knowledge_rag(
        blueprint_dir=ROOT,
        resolved_config={"knowledge_rag": {"enabled": True, "knowledge_dir": "@/payloads/knowledge"}},
        active_knowledge=knowledge.load_vc_knowledge(ROOT),
    )
    assert result["status"] == "ready"
    assert captured["embedder_factory"] is build_runtime_embedder
    assert captured["knowledge_dir"] == ROOT / "payloads/knowledge"


def test_rag_retrieval_injects_gateway_and_preserves_job_storage(monkeypatch, tmp_path):
    from domain import knowledge
    from mn_sdk.integrations.models import RuntimeModelClient

    captured = {}
    monkeypatch.setenv("MN_JOB_ID", "vc-sdk-test")
    monkeypatch.setenv("MN_JOB_DATA_DIR", str(tmp_path / "vc-sdk-test"))
    monkeypatch.setattr(knowledge, "fake_skills_mode_enabled", lambda *_: False)

    def retrieve(**options):
        captured.update(options)
        return {"enabled": True, "status": "ready", "citations": [{"ref": 1}], "context": "Evidence"}

    monkeypatch.setattr(knowledge, "sdk_retrieve_knowledge_rag_context", retrieve)
    result = knowledge.retrieve_knowledge_rag_context(
        knowledge_rag={"enabled": True, "status": "ready", "config": {"required": True}},
        query="Funding evidence",
        stage="funding_researcher",
        company="Acme",
    )
    embedder = captured["embedder"]
    assert isinstance(embedder.runtime, RuntimeModelClient)
    assert Path(embedder.config.db_path) == tmp_path / "vc-sdk-test/databases/rag/milvus.db"
    assert captured["query"] == "Funding evidence"
    assert result["citations"] == [{"ref": 1}]
