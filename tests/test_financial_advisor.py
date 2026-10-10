from __future__ import annotations

import builtins
import importlib
import json

from blueprint_modernization_support import (
    ROOT,
    assert_modular_payload,
    assert_registry_handlers_import,
    blueprint_path,
    expanded_manifest,
    run_payload_script,
    source_manifest,
)
from mn_sdk.bundle_io import load_bundle_payloads

EXPECTED_STEPS = [
    "prepare_financial_packet",
    "analyze_household_finances",
    "prepare_tax_review",
    "analyze_portfolio_risk",
    "collect_public_finance_guidance",
    "reconcile_advisor_evidence",
    "publish_financial_review_packet",
]


def test_financial_intake_uses_current_document_package(monkeypatch, tmp_path):
    original_import = builtins.__import__
    retired = {"mn_document_reading_skill", "mn_llm_ocr_skill", "mn_pdf_extract_skill"}

    def current_packages_only(name, *args, **kwargs):
        if name.split(".", 1)[0] in retired:
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", current_packages_only)
    monkeypatch.syspath_prepend(str(blueprint_path("financial_advisor") / "payloads"))
    intake = importlib.import_module("domain.source_ingestion")
    documents = importlib.import_module("mn_docs_to_markdown_skill")
    assert intake.configure_ocr_runtime is documents.configure_ocr_runtime
    assert intake.extract_document is documents.extract_document
    assert intake.docker_ocr_client_factory_from_config is documents.docker_ocr_client_factory_from_config

    source = tmp_path / "statement.txt"
    source.write_text("Bank statement\nOpening balance: $100.00\n")
    assert intake.iter_input_files(tmp_path) == [source]
    record = intake.read_document(source)
    assert record["kind"] == "bank_statement"
    assert record["fingerprint"]["sha256"] == documents.file_sha256(source)


def test_financial_manifest_compiles_ordered_regulated_state_pipeline():
    source = source_manifest("financial_advisor")
    expanded = expanded_manifest("financial_advisor")
    primary_llm = source["llm"]["configs"]["primary"]

    assert source["llm"]["model"] == "default"
    assert source["llm"]["strict_json"] is True
    assert "model" not in primary_llm
    assert "runtime_model" not in primary_llm
    assert primary_llm["max_tokens"] == 10000
    config = json.loads((blueprint_path("financial_advisor") / "config" / "default.json").read_text())
    assert config["llm"]["strict_json"] is True
    assert config["llm"]["configs"]["primary"]["max_tokens"] == 1200
    assert source["requirements"]["memory"]["min_gb"] == 2
    assert source["requirements"]["gpu"] == {"min_count": 0}
    assert [step["id"] for step in source["workflow"]["steps"]] == EXPECTED_STEPS
    assert [step.get("needs", []) for step in source["workflow"]["steps"]] == [
        [],
        ["prepare_financial_packet"],
        ["analyze_household_finances"],
        ["prepare_tax_review"],
        ["analyze_portfolio_risk"],
        ["collect_public_finance_guidance"],
        ["reconcile_advisor_evidence"],
    ]
    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "prepare_tax_review__capture" in node_ids
    assert "analyze_portfolio_risk__risk" in node_ids
    assert "publish_financial_review_packet__end" in node_ids


def test_financial_workers_stage_the_domain_package():
    blueprint = ROOT.parent / "mn-blueprints" / "financial_advisor"
    expanded = expanded_manifest("financial_advisor")
    executable_nodes = [
        node
        for node in expanded["agents"]["nodes"]
        if (node.get("config") or {}).get("runner_module")
        == "MirrorNeuron.Runner.DockerWorker"
    ]

    assert executable_nodes
    assert all(
        {"source": "domain", "target": "domain"} in node["config"]["upload_paths"]
        for node in executable_nodes
    )

    payloads = load_bundle_payloads(blueprint)
    assert "docker_worker/Dockerfile" in payloads


def test_financial_review_normalization_preserves_structured_model_findings():
    result = run_payload_script(
        "financial_advisor",
        """
import json
from domain.review_services import normalize_review_response

finding = {"kind": "source_gap", "source": "sample-w2.txt"}
normalized = normalize_review_response(
    {"risk_flags": [finding, dict(finding)]},
    {
        "summary": "fallback",
        "risk_flags": ["review source evidence"],
        "confidence": 0.68,
    },
    [],
)
print(json.dumps(normalized))
""",
    )

    assert result["risk_flags"] == [
        "review source evidence",
        {"kind": "source_gap", "source": "sample-w2.txt"},
    ]


def test_portfolio_reviewer_does_not_feed_prior_llm_finding_back_to_model():
    result = run_payload_script(
        "financial_advisor",
        """
import json
from domain.portfolio import step_portfolio_llm_reviewer

class CapturingLLM:
    provider = "test"
    model = "test"
    calls = 0
    fallback_calls = 0
    input_tokens = 0
    output_tokens = 0
    total_tokens = 0
    estimated_tokens = 0

    def generate_json(self, *, user_prompt, fallback, **_kwargs):
        self.calls += 1
        self.user_prompt = user_prompt
        return fallback

llm = CapturingLLM()
ctx = {
    "config": {"llm": {"enabled": True, "configs": {"primary": {}}}},
    "llm": llm,
    "active_knowledge": {},
    "state": {
        "workflow": {
            "portfolio_context_loader": {
                "holding_count": 1,
                "portfolio_source_refs": ["portfolio.json"],
                "risk_policy": {},
                "risk_policy_provenance": {},
                "customer_profile_status": {"missing_fields": []},
            },
            "portfolio_market_data_loader": {
                "provider": "fixture",
                "source_refs": ["fixture:ABC"],
            },
            "portfolio_risk_engine": {
                "total_value": 100.0,
                "cash_weight_pct": 10.0,
                "largest_position_weight_pct": 90.0,
                "largest_position": {"symbol": "ABC", "instrument_type": "stock"},
                "holdings": [{"symbol": "ABC"}],
                "policy_violations": [],
                "screening_threshold_flags": [],
                "warnings": [],
                "actor_finding": {"summary": "PRIOR MODEL NARRATIVE MUST NOT BE RECYCLED"},
            },
        }
    },
}
step_portfolio_llm_reviewer(ctx)
print(json.dumps({"prompt": llm.user_prompt}))
""",
    )

    assert "PRIOR MODEL NARRATIVE MUST NOT BE RECYCLED" not in result["prompt"]
    assert '"total_value": 100.0' in result["prompt"]


def test_financial_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("financial_advisor")
    assert_registry_handlers_import("financial_advisor")
    execution = (
        ROOT.parent
        / "mn-blueprints"
        / "financial_advisor"
        / "payloads"
        / "domain"
        / "execution.py"
    ).read_text()
    assert "workflow_step_id" not in execution
    assert "WORKFLOW_STEPS[-1]" not in execution


def test_financial_runtime_uses_shared_job_context_and_persistence(tmp_path):
    result = run_payload_script(
        "financial_advisor",
        f"""
import json
import os
from pathlib import Path

from domain.runtime_services import build_context
from domain.state import persist_runtime_context, runtime_context_path

documents = Path({str((blueprint_path("financial_advisor") / "examples" / "sample_inputs").resolve())!r})
output_folder = Path({str((tmp_path / "job-output").resolve())!r})
runs_root = Path({str((tmp_path / "runs").resolve())!r})
os.environ['MN_JOB_ID'] = 'financial-runtime-job'
os.environ['MN_WORKFLOW_ATTEMPT_ID'] = 'attempt-3'
os.environ['MN_JOB_OUTPUT_DIR'] = str(output_folder)
os.environ['MN_RUNS_ROOT'] = str(runs_root)

context = build_context(
    inputs={{
        'document_folder': str(documents),
        'output_folder': str(Path({str((tmp_path / "ignored-local-output").resolve())!r})),
    }},
    config={{'llm': {{'mode': 'fake', 'require_live': False}}}},
    config_json=None,
    runs_root=None,
    run_id='financial-runtime-run',
    llm_client=None,
)
persist_runtime_context(context)
stored = json.loads(runtime_context_path(context['run_dir']).read_text(encoding='utf-8'))
print(json.dumps({{
    'job_id': context['job_id'],
    'attempt_id': context['attempt_id'],
    'run_dir': str(context['run_dir']),
    'output_folder': str(context['output_folder']),
    'document_folder': str(context['document_folder']),
    'stored_document_folder': stored['document_folder'],
    'stored_payload_folder': stored['payload']['document_folder'],
}}))
""",
    )

    assert result["job_id"] == "financial-runtime-job"
    assert result["attempt_id"] == "attempt-3"
    assert result["run_dir"] == str(tmp_path / "runs" / "financial-runtime-run")
    assert result["output_folder"] == str(tmp_path / "job-output")
    assert result["document_folder"] == str(
        blueprint_path("financial_advisor") / "examples" / "sample_inputs"
    )
    assert result["stored_document_folder"] == result["document_folder"]
    assert result["stored_payload_folder"] == result["document_folder"]


def test_financial_runtime_reads_staged_folder_when_message_payload_is_dot(tmp_path):
    staged = tmp_path / "staged-documents"
    staged.mkdir()
    (staged / "statement.txt").write_text("Sample statement", encoding="utf-8")
    result = run_payload_script(
        "financial_advisor",
        f"""
import json
from domain.runtime_services import build_context
from domain.intake import step_financial_folder_watcher

context = build_context(
    inputs={{"document_folder": ".", "input_folder": "."}},
    config={{"document_sources": {{"folder_path": {str(staged)!r}}}, "llm": {{"mode": "fake", "require_live": False}}}},
    config_json=None,
    runs_root={str(tmp_path / "runs")!r},
    run_id="staged-folder-test",
    llm_client=None,
)
print(json.dumps({{"folder": str(context["document_folder"]), "files": [item["name"] for item in step_financial_folder_watcher(context)["files"]]}}))
""",
    )
    assert result == {"folder": str(staged), "files": ["statement.txt"]}


def test_financial_sample_builds_customer_and_audit_layers(tmp_path):
    result = run_payload_script(
        "financial_advisor",
        f"""
import json
from pathlib import Path
from domain.composition import run_blueprint

root = Path({str((blueprint_path("financial_advisor")).resolve())!r})
out = Path({str(tmp_path)!r}) / "output"
run = run_blueprint(
    inputs={{"document_folder": str(root / "examples" / "sample_inputs"), "input_folder": str(root / "examples" / "sample_inputs"), "output_folder": str(out), "quick_test": True}},
    config={{"execution": {{"quick_test": True}}}},
    runs_root=out / "runs",
    run_id="financial-quality",
)
artifact = run["final_artifact"]
print(json.dumps({{
    "status": run["status"],
    "cash_flow": artifact["household_finance_summary"]["preliminary_net_cash_flow"],
    "draft_income": artifact["tax_review_packet"]["workpapers"]["draft_income_total"],
    "portfolio_value": artifact["portfolio_risk_review"]["total_value"],
    "profile_status": artifact["portfolio_risk_review"]["suitability_assessment"]["status"],
    "portfolio_readiness": artifact["customer_readiness"]["portfolio"],
    "top_priority": artifact["customer_report"]["top_actions"][0]["priority"],
    "top_action": artifact["customer_report"]["top_actions"][0]["customer_action"],
    "run_artifact_exists": (out / "runs" / "financial-quality" / "final_artifact.json").exists(),
    "customer_report_exists": (out / "customer_report.json").exists(),
}}))
""",
    )
    assert result["status"] == "completed"
    assert result["cash_flow"] == 2394.8599999999997
    assert result["draft_income"] == 88528.44
    assert result["portfolio_value"] == 186000.0
    assert result["profile_status"] == "complete"
    assert "objectives were supplied" in result["portfolio_readiness"]["label"]
    assert "fixture prices" in result["portfolio_readiness"]["label"]
    assert result["top_priority"] == "Critical"
    assert "Schedule E" in result["top_action"]
    assert result["run_artifact_exists"] is True
    assert result["customer_report_exists"] is True


def test_deployed_financial_report_is_run_scoped_and_discoverable_without_finalizing(tmp_path):
    result = run_payload_script(
        "financial_advisor",
        f"""
import hashlib
import json
from pathlib import Path
from domain.composition import LOCAL_AGENT_SEQUENCE
from domain.execution import execute_runtime_handler
from mn_sdk.run_outputs import output_metadata

root = Path({str(blueprint_path("financial_advisor"))!r})
runs = Path({str(tmp_path / "runs")!r})
exports = Path({str(tmp_path / "exports")!r})
proofs = []
for run_id in ('first-review', 'second-review'):
    for agent_id, handler in LOCAL_AGENT_SEQUENCE:
        result = execute_runtime_handler(
            agent_id, handler,
            inputs={{'document_folder': str(root / 'examples' / 'sample_inputs'),
                    'output_folder': str(exports), 'quick_test': True}},
            config={{'execution': {{'quick_test': True}}}},
            runs_root=runs, run_id=run_id,
        )
    directory = runs / run_id
    refs = output_metadata(directory)
    proofs.append({{
        'run_id': json.loads((directory / 'final_artifact.json').read_text())['run_id'],
        'files': [ref['relative_path'] for ref in refs],
        'all_contained': all(not ref['external'] for ref in refs),
        'run_status': json.loads((directory / 'run.json').read_text())['status'],
        'result_exists': (directory / 'result.json').exists(),
        'report_hash': hashlib.sha256((directory / 'financial_advisor_report.md').read_bytes()).hexdigest(),
    }})
first = runs / 'first-review'
print(json.dumps({{'proofs': proofs, 'first_hash_after_second': hashlib.sha256((first / 'financial_advisor_report.md').read_bytes()).hexdigest(),
                  'export_exists': (exports / 'financial_advisor_report.md').exists(),
                  'prepared_report_hashes': sorted(json.loads(p.read_text())['original_sha256']
                    for p in (exports / 'context_sources' / 'outputs').rglob('*.conversion.json'))}}))
""",
    )
    assert [proof["run_id"] for proof in result["proofs"]] == ["first-review", "second-review"]
    for proof in result["proofs"]:
        assert len(proof["files"]) == 14
        assert "financial_advisor_report.md" in proof["files"]
        assert "customer_report.json" in proof["files"]
        assert "final_artifact.json" in proof["files"]
        assert proof["all_contained"] is True
        assert proof["run_status"] == "running"
        assert proof["result_exists"] is False
    assert result["proofs"][0]["report_hash"] == result["first_hash_after_second"]
    assert result["export_exists"] is True
    assert result["prepared_report_hashes"] == sorted(proof["report_hash"] for proof in result["proofs"])
