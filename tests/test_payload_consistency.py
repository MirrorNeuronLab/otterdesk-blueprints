from __future__ import annotations

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
        ROOT / blueprint_id / "payloads" / "document_workflow" / "scripts" / "run_blueprint.py"
        for blueprint_id in (
            "invoice_bill_extraction_assistant",
            "legal_contract_clause_review_assistant",
            "medical_deid_record_intake_assistant",
            "tax_form_ocr_capture_assistant",
        )
    ]
    expected = _document_runner_template(runner_paths[0])
    for path in runner_paths[1:]:
        assert _document_runner_template(path) == expected, path
