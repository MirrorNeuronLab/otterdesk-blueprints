from __future__ import annotations

import json
from pathlib import Path

from blueprint_modernization_support import blueprint_path
from mn_sdk.blueprints import blueprint_definition, read_blueprint

ROOT = Path(__file__).resolve().parents[1]
GTM_PAYLOADS = ROOT / "gtm_ai_workflow" / "payloads"


def _assert_all_identical(paths: list[Path]) -> None:
    assert len(paths) >= 2
    expected = paths[0].read_bytes()
    for path in paths[1:]:
        assert path.read_bytes() == expected, path


def test_gtm_vendored_runtime_and_skill_copies_stay_identical():
    if not GTM_PAYLOADS.exists():
        return

    duplicate_groups = [
        sorted(GTM_PAYLOADS.glob("*/_synaptic_runtime/core.py")),
        sorted(GTM_PAYLOADS.glob("*/_synaptic_skills/email_delivery.py")),
        sorted(GTM_PAYLOADS.glob("*/_synaptic_skills/marketing_email.py")),
        sorted(GTM_PAYLOADS.glob("*/mn_skills/mn_email_send_resend_skill/resend.py")),
        sorted(
            GTM_PAYLOADS.glob(
                "*/mn_skills/mn_email_receive_agentmail_skill/agentmail.py"
            )
        ),
    ]
    for paths in duplicate_groups:
        if len(paths) < 2:
            continue
        _assert_all_identical(paths)


def test_sdk_llm_blueprints_do_not_depend_on_the_communication_skill():
    for blueprint_id in (
        "vc_assistant",
        "financial_advisor",
        "legal_assistant",
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
        read_blueprint(ROOT.parent / "mn-blueprints" / "vc_assistant" / "manifest.json")
    )
    vc_packages = {
        str(item.get("name") or "")
        for item in vc_manifest.get("skill_dependencies") or []
        if isinstance(item, dict)
    }
    assert {"mirrorneuron-rag-skill", "mirrorneuron-llm-ocr-skill"} <= vc_packages


def test_vc_assistant_leaves_rag_and_ocr_model_specs_in_their_skills():
    forbidden_model_text = ("lightonocr", "jina-embeddings", "rag-embedding")
    manifest_path = ROOT.parent / "mn-blueprints" / "vc_assistant" / "manifest.json"
    config_path = (
        ROOT.parent / "mn-blueprints" / "vc_assistant" / "config" / "default.json"
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
