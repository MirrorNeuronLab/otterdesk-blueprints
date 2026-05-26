from __future__ import annotations

import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest


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
POST_LAUNCH_PATH = ROOT / "personal_income_tax_expert" / "scripts" / "post-launch.sh"


def _load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_runner():
    return _load_module(RUNNER_PATH, "personal_income_tax_expert_runner")


class EchoingHugeLLM:
    provider = "test"
    model = "huge-echo-test"

    def __init__(self):
        self.calls = 0
        self.fallback_calls = 0

    def generate_json(self, *, system_prompt, user_prompt, fallback):
        self.calls += 1
        response = dict(fallback)
        response["payload_echo"] = "x" * 5_000_000
        if "advisor_message" in response:
            response["advisor_message"] = "A" * 80_000
        return response


@pytest.fixture(autouse=True)
def clear_blueprint_config_env(monkeypatch):
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_JSON", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_PATH", raising=False)


def test_personal_tax_expert_speaks_like_advisor_and_prepares_1040_packet(tmp_path):
    runner = _load_runner()
    output_dir = tmp_path / "exports"

    result = runner.run_blueprint(
        config={
            "llm": {"mode": "fake"},
            "tax_documents": {"folder_path": ""},
            "inputs": {"payload": {"document_folder": ""}},
            "outputs": {"folder_path": str(output_dir)},
        },
        runs_root=tmp_path,
        run_id="tax-advisor-unit",
    )
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
    assert "document_dossier" in artifact
    assert "preparer_workpapers" in artifact
    assert "audit_review" in artifact
    assert "manager_review" in artifact
    assert artifact["manager_review"]["manager_signoff"] == "not_approved_for_filing"
    assert result["llm"]["calls"] == result["llm"]["specialist_stage_count"] == 9
    assert any(item["agent"] == "tax_auditor" for item in result["timeline"])
    assert any(item["agent"] == "manager_reviewer" for item in result["timeline"])
    assert (tmp_path / "tax-advisor-unit" / "final_artifact.json").exists()
    output_kinds = {item["kind"] for item in result["output_files"]}
    assert output_kinds == {"final_artifact_json", "report_markdown", "tax_review_packet_pdf"}
    for item in result["output_files"]:
        assert Path(item["path"]).exists()

    reader = pytest.importorskip("pypdf").PdfReader(
        next(Path(item["path"]) for item in result["output_files"] if item["kind"] == "tax_review_packet_pdf")
    )
    pdf_text = "\n".join(page.extract_text() or "" for page in reader.pages)
    assert "Prepared Form 1040 Draft" in pdf_text
    assert "Draft review packet only" in pdf_text
    assert "Draft Form 1040 Line Map" in pdf_text
    assert "Manager Review And Signoff" in pdf_text


def test_personal_tax_expert_reads_local_folder_fixture(tmp_path):
    runner = _load_runner()
    docs = tmp_path / "tax-docs"
    docs.mkdir()
    (docs / "bank-1099-int.txt").write_text(
        "Form 1099-INT Interest Income. Box 1 interest income 55.25.",
        encoding="utf-8",
    )
    config = {
        "llm": {"mode": "fake"},
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
        "outputs": {"folder_path": str(tmp_path / "exports")},
    }

    result = runner.run_blueprint(config=config, runs_root=tmp_path, run_id="tax-folder-unit")

    assert result["document_summary"]["document_types"]["1099-INT"] == 1
    assert result["final_artifact"]["prepared_form_1040"]["line_map"]["2b_taxable_interest"] == "$55.25"
    assert result["llm"]["calls"] == 9


def test_personal_tax_expert_compacts_huge_llm_echo_for_transport(tmp_path):
    runner = _load_runner()
    llm = EchoingHugeLLM()
    result = runner.run_blueprint(
        llm_client=llm,
        config={
            "tax_documents": {"folder_path": ""},
            "inputs": {"payload": {"document_folder": ""}},
            "outputs": {"folder_path": str(tmp_path / "exports")},
        },
        runs_root=tmp_path,
        run_id="tax-huge-echo-unit",
    )

    encoded = json.dumps(result, sort_keys=True).encode("utf-8")
    assert len(encoded) < 4_000_000
    assert "payload_echo" not in encoded.decode("utf-8", errors="ignore")
    assert result["llm"]["calls"] == 9
    assert result["final_artifact"]["prepared_form_1040"]["line_map"]["1z_wages"] == "$86,000.00"


def test_personal_tax_post_launch_materializes_host_outputs(tmp_path):
    runner = _load_runner()
    run_id = "personal_income_tax_expert-post-launch-unit"
    output_dir = tmp_path / "host-exports"
    result = runner.run_blueprint(
        config={
            "llm": {"mode": "fake"},
            "tax_documents": {"folder_path": ""},
            "inputs": {"payload": {"document_folder": ""}},
            "outputs": {"folder_path": str(tmp_path / "sandbox-exports")},
        },
        runs_root=tmp_path / "sandbox-runs",
        run_id=run_id,
    )
    result["config"]["outputs"]["folder_path"] = str(output_dir)
    result["final_artifact"].pop("output_files", None)

    run_dir = tmp_path / "host-runs" / run_id
    run_dir.mkdir(parents=True)
    (run_dir / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "job_completed",
                "result": {
                    "count": 1,
                    "last_message": {
                        "sandbox": {
                            "logs": json.dumps(result),
                        }
                    },
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    env = os.environ.copy()
    env.update({"MN_RUN_DIR": str(run_dir), "MN_RUN_ID": run_id, "MN_RUNS_ROOT": str(run_dir.parent)})
    subprocess.run(["bash", str(POST_LAUNCH_PATH)], check=True, env=env, cwd=POST_LAUNCH_PATH.parent)

    assert (run_dir / "result.json").exists()
    assert (run_dir / "final_artifact.json").exists()
    artifact = json.loads((run_dir / "final_artifact.json").read_text())
    output_kinds = {item["kind"] for item in artifact["output_files"]}
    assert output_kinds == {"final_artifact_json", "report_markdown", "tax_review_packet_pdf"}
    assert (output_dir / f"{run_id}-final-artifact.json").exists()
    assert (output_dir / f"{run_id}-report.md").read_text().startswith("# Prepared Form 1040 Draft")
    assert (output_dir / f"{run_id}-tax-review-packet.pdf").exists()


def test_personal_tax_expert_reads_staged_env_config_folder(tmp_path, monkeypatch):
    runner = _load_runner()
    docs = tmp_path / "mn_local_inputs" / "tax_documents"
    docs.mkdir(parents=True)
    (docs / "w2.txt").write_text(
        "Form W-2 Wage and Tax Statement. Box 1 wages 123456.00. Box 2 federal income tax withheld 22000.00.",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps(
            {
                "llm": {"mode": "fake"},
                "tax_documents": {
                    "folder_path": "mn_local_inputs/tax_documents",
                    "recommended_forms": ["W-2"],
                },
                "inputs": {
                    "payload": {
                        "document_folder": "mn_local_inputs/tax_documents",
                        "filing_status": "single",
                        "tax_year": 2025,
                    }
                },
                "outputs": {"folder_path": str(tmp_path / "exports")},
            }
        ),
    )

    result = runner.run_blueprint(runs_root=tmp_path, run_id="tax-staged-env-unit")

    assert result["document_summary"]["document_types"]["W-2"] == 1
    assert result["final_artifact"]["prepared_form_1040"]["line_map"]["1z_wages"] == "$123,456.00"
    assert "A real local tax document folder has not been provided." not in result["warnings"]


def test_personal_tax_folder_validator_accepts_demo_mode(monkeypatch, capsys):
    validator = _load_module(VALIDATOR_PATH, "personal_income_tax_expert_validator")
    monkeypatch.setenv("MN_BLUEPRINT_CONFIG_JSON", json.dumps({"tax_documents": {"folder_path": ""}}))

    assert validator.main() == 0
    assert "demo sample documents" in capsys.readouterr().out


def test_personal_tax_folder_validator_accepts_staged_runtime_path(tmp_path, monkeypatch, capsys):
    validator = _load_module(VALIDATOR_PATH, "personal_income_tax_expert_staged_validator")
    staged = tmp_path / "payloads" / "tax_workflow" / "mn_local_inputs" / "tax_documents"
    staged.mkdir(parents=True)
    (staged / "w2.txt").write_text("Form W-2 Box 1 wages 100", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps(
            {
                "tax_documents": {"folder_path": "mn_local_inputs/tax_documents"},
                "local_inputs": {
                    "folders": [
                        {
                            "config_path": "tax_documents.folder_path",
                            "payload_path": "tax_workflow/mn_local_inputs/tax_documents",
                            "runtime_path": "mn_local_inputs/tax_documents",
                        }
                    ]
                },
            }
        ),
    )

    assert validator.main() == 0
    assert "Validated tax document folder with 1 candidate" in capsys.readouterr().out
