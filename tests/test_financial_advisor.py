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
    assert source["llm"]["context_size"] == 8192
    assert primary_llm["max_tokens"] == 1200
    config = json.loads((blueprint_path("financial_advisor") / "config" / "default.json").read_text())
    assert config["llm"]["strict_json"] is True
    assert config["llm"]["configs"]["primary"]["max_tokens"] == 1800
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


def test_financial_model_settings_allow_local_review_time_in_the_runtime_client(monkeypatch):
    from dataclasses import replace

    from mn_sdk.blueprint_support import runtime as llm_runtime
    from mn_sdk.blueprints import read_blueprint, resolve_config
    from mn_sdk.llm import resolve_config as resolve_llm_config

    # Keep operator registry and live endpoints outside this configuration test.
    monkeypatch.setattr(llm_runtime, "select_default_model", lambda *_args, **_kwargs: {
        "model": "default", "selected_model": "small",
        "provider": "docker_model_runner",
    })
    monkeypatch.setattr(llm_runtime, "resolve_model_entry", lambda *_args, **_kwargs: {})
    clients = {}
    for blueprint_id in ("financial_advisor", "vc_assistant"):
        config = resolve_config(read_blueprint(blueprint_path(blueprint_id))).data
        environment = llm_runtime.configured_llm_environment(
            config, env={"MN_RUNTIME_MODEL_MANAGED": "1"},
        )
        clients[blueprint_id] = resolve_llm_config(environment)

    financial = clients["financial_advisor"]
    assert financial == replace(clients["vc_assistant"], timeout_seconds=300)
    assert financial.model == "default"
    assert financial.provider == "docker_model_runner"
    assert financial.backend == "llama.cpp"
    assert financial.context_size == 8192
    assert financial.max_tokens == 1800
    assert financial.timeout_seconds == 300
    assert financial.num_retries == 2
    assert financial.retry_backoff_seconds == 1.0

    # A run-specific deadline must still override the operator default.
    config = resolve_config(read_blueprint(blueprint_path("financial_advisor"))).data
    config["llm"]["configs"]["primary"]["timeout_seconds"] = 45
    environment = llm_runtime.configured_llm_environment(
        config, env={"MN_RUNTIME_MODEL_MANAGED": "1"},
    )
    assert resolve_llm_config(environment).timeout_seconds == 45


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
from tempfile import TemporaryDirectory
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.contracts import fingerprint
from mn_sdk_common.committed_artifacts import CommittedJsonStore
with TemporaryDirectory() as directory:
    ctx["config"]["execution"] = {"quick_test": True}
    block = BlockContext(store=CommittedJsonStore(directory), config=ctx["config"], invocation_id="portfolio-review", revision="test", resources={"llm": llm})
    state = {**ctx["state"], "configuration": fingerprint(block.config), "inputs": {}, "knowledge": {}}
    reference = block.store.commit("fixture.json", state).to_dict()
    step_portfolio_llm_reviewer(block, {"result": {"state": reference}})
print(json.dumps({"prompt": llm.user_prompt}))
""",
    )

    assert "PRIOR MODEL NARRATIVE MUST NOT BE RECYCLED" not in result["prompt"]
    assert '"total_value": 100.0' in result["prompt"]


def test_financial_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("financial_advisor")
    assert_registry_handlers_import("financial_advisor")
    payload = blueprint_path("financial_advisor") / "payloads"
    assert not (payload / "domain" / "execution.py").exists()
    assert not (payload / "domain" / "runtime_services.py").exists()
    assert not list((payload / "runtime").glob("*.py"))


def test_financial_native_intake_uses_sdk_identity_and_job_output(tmp_path):
    result = run_payload_script("financial_advisor", f"""
import json, os
from pathlib import Path
from mn_sdk.step_runtime import StepContext
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_blueprint_blocks.context import BlockContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from domain.intake import step_financial_folder_watcher
root = Path({str(blueprint_path("financial_advisor"))!r})
os.environ.update(MN_JOB_ID='financial-runtime-job', MN_WORKFLOW_ATTEMPT_ID='attempt-3', MN_RUN_ID='financial-runtime-run', MN_JOB_OUTPUT_DIR={str(tmp_path / 'job-output')!r})
context = StepContext.from_environment()
block = BlockContext(store=CommittedJsonStore(Path({str(tmp_path / 'runs')!r}) / context.run_id),
    config=resolve_config(read_blueprint(root), {{'execution': {{'quick_test': True}}}}).data,
    job_id=context.job_id, run_id=context.run_id, invocation_id='intake', revision='test')
first = step_financial_folder_watcher(block, {{'request': {{'document_folder': str(root / 'examples/sample_inputs'), 'output_folder': 'ignored-local-output'}}}})
assert step_financial_folder_watcher(block, {{'request': {{'document_folder': str(root / 'examples/sample_inputs'), 'output_folder': 'ignored-local-output'}}}}) == first
state = block.store.read(first['state'])
print(json.dumps({{'job_id': block.job_id, 'attempt_id': context.attempt_id, 'run_dir': str(block.store.run_dir),
    'output_folder': str(block.output_directory), 'document_folder': state['inputs']['document_folder'],
    'stored_payload_folder': block.store.read(state['input_artifact'])['document_folder']}}))
""")
    assert result['job_id'] == 'financial-runtime-job' and result['attempt_id'] == 'attempt-3'
    assert result['run_dir'] == str(tmp_path / 'runs/financial-runtime-run')
    assert result['output_folder'] == str(tmp_path / 'job-output')
    assert result['document_folder'] == result['stored_payload_folder'] == str(blueprint_path('financial_advisor') / 'examples/sample_inputs')


def test_financial_native_intake_reads_staged_folder_when_message_omits_paths(tmp_path):
    staged = tmp_path / 'staged-documents'
    staged.mkdir()
    (staged / 'statement.txt').write_text('Sample statement')
    result = run_payload_script('financial_advisor', f"""
import json
from mn_sdk.blueprints import read_blueprint, resolve_config
from mn_blueprint_blocks.context import BlockContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore
from domain.intake import step_financial_folder_watcher
block = BlockContext(store=CommittedJsonStore({str(tmp_path / 'run')!r}), invocation_id='intake', revision='test',
    config=resolve_config(read_blueprint({str(blueprint_path('financial_advisor'))!r}), {{'document_sources': {{'folder_path': {str(staged)!r}}}, 'execution': {{'quick_test': True}}}}).data)
result = step_financial_folder_watcher(block, {{'request': {{'document_folder': None, 'input_folder': None}}}})
state = block.store.read(result['state'])
print(json.dumps({{'folder': state['inputs']['document_folder'], 'files': [item['name'] for item in state['workflow']['financial_folder_watcher']['files']]}}))
""")
    assert result == {'folder': str(staged), 'files': ['statement.txt']}


def test_financial_sample_builds_customer_and_audit_layers(tmp_path):
    result = run_payload_script(
        "financial_advisor",
        f"""
import json
from pathlib import Path
from functools import partial
from block_workflow_fixture import run_sample
run_blueprint = partial(run_sample, 'financial_advisor')

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
    "customer_report_exists": (out / "runs" / "financial-quality" / "customer_report.json").exists(),
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
from block_workflow_fixture import run_sample
from mn_sdk.run_outputs import output_metadata

root = Path({str(blueprint_path("financial_advisor"))!r})
runs = Path({str(tmp_path / "runs")!r})
exports = Path({str(tmp_path / "exports")!r})
proofs = []
for run_id in ('first-review', 'second-review'):
    result = run_sample('financial_advisor',
        inputs={{'document_folder': str(root / 'examples' / 'sample_inputs'),
                'output_folder': str(exports), 'quick_test': True}},
        config={{'execution': {{'quick_test': True}}}},
        runs_root=runs, run_id=run_id)
    directory = runs / run_id
    refs = output_metadata(directory)
    proofs.append({{
        'run_id': json.loads((directory / 'final_artifact.json').read_text())['run_id'],
        'files': [ref['relative_path'] for ref in refs],
        'all_contained': all(not ref['external'] for ref in refs),
        'run_metadata_exists': (directory / 'run.json').exists(),
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
        assert len(proof["files"]) == 15
        assert "financial_advisor_report.md" in proof["files"]
        assert "customer_report.json" in proof["files"]
        assert "final_artifact.json" in proof["files"]
        assert proof["all_contained"] is True
        assert proof["run_metadata_exists"] is False
        assert proof["result_exists"] is True
    assert result["proofs"][0]["report_hash"] == result["first_hash_after_second"]
    assert result["export_exists"] is True
    assert result["prepared_report_hashes"] == sorted(proof["report_hash"] for proof in result["proofs"])


def test_saved_financial_rules_reach_review_prompts_without_changing_calculations(tmp_path, monkeypatch):
    from mn_blueprint_blocks.context import BlockContext
    from mn_sdk_common.committed_artifacts import CommittedJsonStore

    monkeypatch.syspath_prepend(str(ROOT / "financial_advisor/payloads"))
    reviews = importlib.import_module("domain.review_services")
    class Model:
        provider = "test"
        model = "test"
        calls = 0
        fallback_calls = 0
        def generate_json(self, **request):
            self.calls += 1
            self.request = request
            return request["fallback"]
    model = Model()
    config = {"llm": {"enabled": True, "configs": {"primary": {}}}, "execution": {"quick_test": True}}
    block = BlockContext(store=CommittedJsonStore(tmp_path), config=config, invocation_id="review", revision="financial_advisor@4.1.0", resources={"llm": model})
    rule = {"id": "cash-first", "kind": "work_rule", "text": "Explain cash reserve evidence before allocation scenarios."}
    state = {"inputs": {"supervisor_instructions": [rule]}, "knowledge": {}}
    evidence = {"total_value": 100.0, "missing_cost_basis": True}
    reviews.actor_review(block, state, "portfolio_llm_reviewer", "Review the saved evidence", evidence)
    prompt = json.loads(model.request["user_prompt"])
    assert prompt["context"]["supervisor_preferences"]["instructions"] == [rule]
    assert "cannot change deterministic" in prompt["context"]["supervisor_preferences"]["boundary"]
    assert prompt["context"]["total_value"] == 100.0
    assert prompt["context"]["missing_cost_basis"] is True
    assert evidence == {"total_value": 100.0, "missing_cost_basis": True}


def test_financial_intake_captures_saved_rules_once_and_rejects_invalid_shapes(tmp_path, monkeypatch):
    import copy
    import pytest
    from jsonschema import ValidationError
    from mn_blueprint_blocks.context import BlockContext
    from mn_sdk.blueprints import read_blueprint, resolve_config
    from mn_sdk_common.committed_artifacts import CommittedJsonStore

    monkeypatch.syspath_prepend(str(ROOT / "financial_advisor/payloads"))
    intake = importlib.import_module("domain.intake")
    config = resolve_config(read_blueprint(ROOT / "financial_advisor")).data
    config["inputs"]["payload"]["supervisor_instructions"] = [{"id": "cash", "kind": "work_rule", "text": "Review reserve evidence first."}]
    block = BlockContext(store=CommittedJsonStore(tmp_path / "one"), config=config, invocation_id="capture", revision="financial_advisor@4.1.0")
    result = intake.step_financial_folder_watcher(block, {"request": {}})
    saved = block.store.read(result["state"])
    assert saved["inputs"]["supervisor_instructions"][0]["text"] == "Review reserve evidence first."
    assert saved["supervisor_instruction_revision"]
    assert intake.step_financial_folder_watcher(block, {"request": {}})["state"] == result["state"]
    invalid = copy.deepcopy(config)
    invalid["inputs"]["payload"]["supervisor_instructions"] = [{"id": "bad", "kind": "permission", "text": "Trade automatically"}]
    other = BlockContext(store=CommittedJsonStore(tmp_path / "invalid"), config=invalid, invocation_id="invalid", revision="financial_advisor@4.1.0")
    with pytest.raises(ValidationError):
        intake.step_financial_folder_watcher(other, {"request": {}})
