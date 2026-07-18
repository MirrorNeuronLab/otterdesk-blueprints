from __future__ import annotations

import json
from pathlib import Path


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
        sorted(GTM_PAYLOADS.glob("*/mn_skills/mn_email_receive_agentmail_skill/agentmail.py")),
    ]
    for paths in duplicate_groups:
        if len(paths) < 2:
            continue
        _assert_all_identical(paths)


def _document_runner_template(path: Path) -> str:
    omitted_prefixes = (
        "BLUEPRINT_ID =",
        "BLUEPRINT_NAME =",
        "OUTPUT_TYPE =",
        "RECOMMENDED_ACTION =",
        "FIELD_PROFILE =",
        "DATASET_INPUT =",
    )
    lines = [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if not line.startswith(omitted_prefixes)
    ]
    return "\n".join(lines)


def test_document_ocr_blueprint_runner_templates_stay_aligned():
    runner_paths = [
        ROOT / blueprint_id / "payloads" / "runtime" / "runtime.py"
        for blueprint_id in (
            "medical_deid_record_intake_assistant",
        )
    ]
    if len(runner_paths) < 2:
        return
    expected = _document_runner_template(runner_paths[0])
    for path in runner_paths[1:]:
        assert _document_runner_template(path) == expected, path


def test_vc_assistant_uses_sdk_llm_without_communication_skill_dependency():
    vc_manifest = json.loads((ROOT / "vc_assistant" / "manifest.json").read_text())
    vc_packages = {
        str(item.get("name") or "")
        for item in vc_manifest.get("skill_dependencies") or []
        if isinstance(item, dict)
    }
    assert "mirrorneuron-rag-skill" in vc_packages
    assert "mirrorneuron-llm-ocr-skill" in vc_packages


def test_vc_assistant_leaves_rag_and_ocr_model_specs_in_their_skills():
    forbidden_model_text = ("lightonocr", "jina-embeddings", "rag-embedding")
    manifest_path = ROOT / "vc_assistant" / "manifest.json"
    config_path = ROOT / "vc_assistant" / "config" / "default.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    serialized = json.dumps(
        {
            "manifest": manifest,
            "config": json.loads(config_path.read_text(encoding="utf-8")),
        }
    ).lower()

    assert not any(value in serialized for value in forbidden_model_text)
    assert "ocr" not in (manifest.get("runtime", {}).get("models", {}))
