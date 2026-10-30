from __future__ import annotations

import json
from pathlib import Path

from blueprint_modernization_support import blueprint_path
from mn_sdk.blueprints import blueprint_definition, read_blueprint

ROOT = Path(__file__).resolve().parents[1]






def test_sdk_llm_blueprints_do_not_depend_on_the_communication_skill():
    for blueprint_id in (
        "vc_assistant",
        "research_assistant",
    ):
        manifest = blueprint_definition(
            read_blueprint(blueprint_path(blueprint_id) / "manifest.json")
        )
        packages = {
            str(item.get("name") or "")
            for item in manifest.get("skill_dependencies") or []
            if isinstance(item, dict)
        }
        assert "mirrorneuron-litellm-communicate-skill" not in packages

    vc_manifest = blueprint_definition(
        read_blueprint(ROOT / "vc_assistant" / "manifest.json")
    )
    vc_packages = {
        str(item.get("name") or "")
        for item in vc_manifest.get("skill_dependencies") or []
        if isinstance(item, dict)
    }
    assert {"mirrorneuron-docs-to-markdown-skill"} <= vc_packages


def test_vc_assistant_leaves_rag_and_ocr_model_specs_in_their_skills():
    forbidden_model_text = ("lightonocr", "jina-embeddings", "rag-embedding")
    manifest_path = ROOT / "vc_assistant" / "manifest.json"
    config_path = (
        ROOT / "vc_assistant" / "config" / "default.json"
    )
    manifest = blueprint_definition(read_blueprint(manifest_path))
    serialized = json.dumps(
        {
            "manifest": manifest,
            "config": json.loads(config_path.read_text(encoding="utf-8")),
        }
    ).lower()

    assert not any(value in serialized for value in forbidden_model_text)
    assert "ocr" not in (manifest.get("runtime", {}).get("models", {}))
