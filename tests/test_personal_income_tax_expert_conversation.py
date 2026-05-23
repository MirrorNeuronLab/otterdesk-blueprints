from __future__ import annotations

import importlib.util
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = (
    ROOT
    / "personal_income_tax_expert"
    / "payloads"
    / "tax_workflow"
    / "scripts"
    / "run_blueprint.py"
)
VALIDATOR_PATH = ROOT / "personal_income_tax_expert" / "payloads" / "validation" / "validate_tax_folder.py"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runner():
    return _load_module(RUNNER_PATH, "personal_income_tax_expert_runner")


def test_personal_tax_expert_speaks_like_advisor_and_prepares_1040_packet(tmp_path):
    runner = _load_runner()

    result = runner.run_blueprint(runs_root=tmp_path, run_id="tax-advisor-unit")
    artifact = result["final_artifact"]

    assert artifact["type"] == "prepared_1040_tax_packet"
    assert artifact["status"] == "draft_needs_review"
    assert artifact["title"] == "Prepared Form 1040 Draft - What Is a 1040 Tax Form"
    assert "Form 1040 is the main U.S. individual income tax return" in artifact["what_is_a_1040_tax_form"]
    assert artifact["prepared_form_1040"]["line_map"]["1z_wages"] == "$86,000.00"
    assert artifact["prepared_form_1040"]["line_map"]["2b_taxable_interest"] == "$128.44"
    assert artifact["prepared_form_1040"]["line_map"]["4b_taxable_ira_pensions_annuities"] == "$2,400.00"
    assert "I took a first pass through your tax packet" in artifact["advisor_message"]
    assert "Before we treat this as ready" in artifact["advisor_message"]
    assert artifact["conversation_context"]["advisor_voice"] == "personal_tax_advisor"
    assert any(item["agent"] == "tax_review_agent" for item in result["timeline"])
    assert (tmp_path / "tax-advisor-unit" / "final_artifact.json").exists()


def test_personal_tax_expert_reads_local_folder_fixture(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "tax-docs"
    docs.mkdir()
    (docs / "bank-1099-int.txt").write_text(
        "Form 1099-INT Interest Income. Box 1 interest income 55.25.",
        encoding="utf-8",
    )
    config = {
        "tax_documents": {
            "folder_path": str(docs),
            "recommended_forms": ["1099-INT"],
        },
        "inputs": {
            "payload": {
                "document_folder": str(docs),
                "filing_status": "single",
                "tax_year": 2025,
            }
        },
    }

    result = runner.run_blueprint(config=config, runs_root=tmp_path, run_id="tax-folder-unit")

    assert result["document_summary"]["document_types"]["1099-INT"] == 1
    assert result["final_artifact"]["prepared_form_1040"]["line_map"]["2b_taxable_interest"] == "$55.25"


def test_personal_tax_folder_validator_accepts_demo_mode(monkeypatch, capsys):
    validator = _load_module(VALIDATOR_PATH, "personal_income_tax_expert_validator")
    monkeypatch.setenv("MN_BLUEPRINT_CONFIG_JSON", json.dumps({"tax_documents": {"folder_path": ""}}))

    assert validator.main() == 0
    assert "demo sample documents" in capsys.readouterr().out
