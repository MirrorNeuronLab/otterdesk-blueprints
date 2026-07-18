from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
RUNNER_PATH = ROOT / "financial_advisor" / "payloads" / "runtime" / "runtime.py"
HEAVY_STEPS = {
    "tax_workpaper_preparer",
    "tax_llm_reviewer",
    "portfolio_risk_engine",
    "portfolio_llm_reviewer",
    "advisor_review_auditor",
    "financial_advice_reporter",
}


def _load_runner():
    spec = importlib.util.spec_from_file_location("financial_advisor_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


class FakeFinancialLLM:
    provider = "fake"
    model = "fake-financial-advisor"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0
        self.prompts: list[dict[str, str]] = []

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        self.prompts.append({"system": system_prompt, "user": user_prompt})
        response = dict(fallback)
        response["summary"] = response.get("summary") or "Fake advisor review completed."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


def _expand_source_manifest(source: dict) -> dict:
    sdk_root = ROOT.parent / "mn-python-sdk" / "mn_sdk"
    package_spec = importlib.util.spec_from_file_location(
        "mn_sdk",
        sdk_root / "__init__.py",
        submodule_search_locations=[str(sdk_root)],
    )
    package = importlib.util.module_from_spec(package_spec)
    package.__path__ = [str(sdk_root)]
    sys.modules.setdefault("mn_sdk", package)
    profiles_spec = importlib.util.spec_from_file_location(
        "mn_sdk.manifest_profiles",
        sdk_root / "manifest_profiles" / "__init__.py",
        submodule_search_locations=[str(sdk_root / "manifest_profiles")],
    )
    profiles = importlib.util.module_from_spec(profiles_spec)
    assert profiles_spec and profiles_spec.loader
    sys.modules["mn_sdk.manifest_profiles"] = profiles
    profiles_spec.loader.exec_module(profiles)

    spec = importlib.util.spec_from_file_location(
        "mn_sdk.manifest_converter",
        sdk_root / "manifest_converter.py",
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules["mn_sdk.manifest_converter"] = module
    spec.loader.exec_module(module)

    return module.expand_manifest_source(source, root_dir=ROOT / "financial_advisor")


def test_financial_advisor_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v2"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["identity"]["id"] == "financial_advisor"
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == [
        "financial_folder_watcher",
        "financial_document_reader",
        "bank_statement_extractor",
        "cash_flow_normalizer",
        "cash_flow_llm_analyst",
        "tax_document_router",
        "tax_form_ocr_capturer",
        "tax_workpaper_preparer",
        "tax_llm_reviewer",
        "portfolio_context_loader",
        "portfolio_market_data_loader",
        "portfolio_risk_engine",
        "portfolio_llm_reviewer",
        "public_finance_researcher",
        "advisor_evidence_reconciler",
        "advisor_review_auditor",
        "financial_advice_reporter",
    ]
    assert all(isinstance(step["needs"], list) for step in manifest["workflow"]["steps"])
    assert all("handler" in step["run"] for step in manifest["workflow"]["steps"])
    assert all(":" not in step["run"]["handler"] for step in manifest["workflow"]["steps"])
    assert manifest["agents"]["extra_templates"] == [
        {
            "node_id": "report_sink",
            "uses": "mn-agents.control.terminal_sink@1",
            "with": {"stereotype": "terminal_report_sink"},
        }
    ]
    groups = manifest["workers"]["groups"]
    assert any(group["with"]["stereotype"] == "public_browser_worker" for group in groups)
    assert any(group["with"]["stereotype"] == "internal_write_worker" for group in groups)
    assert manifest["runtime"]["models"]["ocr"] == {
        "provider": "docker_model_runner",
        "model": "hf.co/noctrex/LightOnOCR-2-1B-GGUF:Q4_K_M",
        "runtime_model": "hf.co/noctrex/LightOnOCR-2-1B-GGUF:Q4_K_M",
        "backend": "llama.cpp",
        "context_size": 4096,
        "required": True,
        "purpose": "document_ocr",
    }
    ocr_config = json.loads((ROOT / "financial_advisor" / "config" / "default.json").read_text(encoding="utf-8"))["input_skills"]["llm_ocr"]
    assert ocr_config["install_policy"] == "runtime"
    assert ocr_config["model"] == "hf.co/noctrex/LightOnOCR-2-1B-GGUF:Q4_K_M"


def test_financial_advisor_model_profiles_assign_large_to_heavy_nodes():
    config = json.loads((ROOT / "financial_advisor" / "config" / "default.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))

    assert config["llm"]["model"] == "default"
    assert "runtime_model" not in config["llm"]
    assert "preferred_model" not in config["llm"]
    assert "model" not in config["llm"]["configs"]["primary"]
    assert set(config["llm"]["configs"]) == {"primary"}
    assert "large_model_profile" not in config["llm"]
    for step, spec in config["llm"]["agents"].items():
        assert spec["llm_config"] == "primary", step

    by_step = manifest["workers"]["by_step"]
    assert set(by_step) == HEAVY_STEPS
    assert all(item["with"]["llm_config"] == "primary" for item in by_step.values())
    assert config["execution_model"] == {
        "type": "manifest_dag",
        "runtime_note": "Topology, dependencies, handlers, and terminal routing are declared only in manifest.json.",
    }


def test_financial_advisor_source_manifest_expands_with_terminal_sink():
    source = json.loads((ROOT / "financial_advisor" / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "report_sink" in node_ids
    assert "financial_advice_reporter" in node_ids
    assert any(
        edge["from_node"] == "financial_advice_reporter" and edge["to_node"] == "report_sink"
        for edge in expanded["agents"]["edges"]
    )
    rendered_reporter = next(node for node in expanded["agents"]["nodes"] if node["node_id"] == "financial_advice_reporter")
    assert rendered_reporter["config"]["llm_config"] == "primary"
    assert rendered_reporter["config"]["environment"]["MN_LLM_CONFIG"] == "primary"
    assert expanded["runtime"]["resources"]["gpu"] == {"min_count": 0}


def test_financial_advisor_runner_resolves_config_from_docker_worker_attempt_root(monkeypatch, tmp_path):
    runner = _load_runner()
    attempt_root = tmp_path / "runs" / "financial_folder_watcher" / "i1-a1-23108"
    script_path = attempt_root / "runtime" / "runtime.py"
    config_path = attempt_root / "config" / "default.json"
    script_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "identity": {"blueprint_id": "financial_advisor"},
                "inputs": {"payload": {"document_folder": "docs", "output_folder": str(tmp_path / "out")}},
                "outputs": {"folder_path": str(tmp_path / "out")},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_PATH", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_BUNDLE_DIR", raising=False)
    monkeypatch.delenv("MN_BLUEPRINT_CONFIG_JSON", raising=False)
    monkeypatch.setattr(runner, "__file__", str(script_path))

    assert script_path.parents[3] != attempt_root
    assert runner.default_config_path() == config_path
    assert runner.blueprint_dir() == attempt_root
    assert runner.load_resolved_config()["identity"]["blueprint_id"] == "financial_advisor"


def test_financial_advisor_runtime_step_handler_writes_step_state(tmp_path):
    runner = _load_runner()
    output_folder = tmp_path / "out"
    result = runner.run_runtime_step(
        "financial_folder_watcher",
        inputs={
            "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "output_folder": str(output_folder),
        },
        runs_root=tmp_path / "runs",
        run_id="financial-advisor-step",
        llm_client=FakeFinancialLLM(),
    )

    run_dir = tmp_path / "runs" / "financial-advisor-step"
    assert result["run_id"] == "financial-advisor-step"
    assert result["workflow_step_id"] == "financial_folder_watcher"
    assert result["runtime_step_mode"] == "workflow_step_handler"
    assert result["outputs"]["output_folder"] == str(output_folder.resolve())
    assert (run_dir / "financial_folder_watcher_result.json").exists()
    assert (run_dir / "workflow_state" / "financial_folder_watcher_result.json").exists()
    assert (run_dir / "workflow_state" / "runtime_context.json").exists()
    assert (run_dir / "workflow_state" / "state.json").exists()
    assert not (output_folder / "final_artifact.json").exists()


def test_financial_advisor_runtime_prefers_shared_output_mount(tmp_path, monkeypatch):
    runner = _load_runner()
    runtime_output = tmp_path / "runtime" / "outputs" / "user"
    runtime_runs = tmp_path / "runtime" / "outputs" / "runs"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(runtime_output))
    monkeypatch.setenv("MN_RUNS_ROOT", str(runtime_runs))

    result = runner.run_runtime_step(
        "financial_folder_watcher",
        inputs={
            "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
        },
        run_id="financial-advisor-runtime-mount",
        llm_client=FakeFinancialLLM(),
    )

    run_dir = runtime_runs / "financial-advisor-runtime-mount"
    assert result["outputs"]["output_folder"] == str(runtime_output.resolve())
    assert run_dir.exists()
    assert (run_dir / "workflow_state" / "runtime_context.json").exists()


def test_financial_advisor_smoke_run_writes_integrated_artifacts(tmp_path):
    runner = _load_runner()
    llm = FakeFinancialLLM()
    output_folder = tmp_path / "out"
    result = runner.run_blueprint(
        inputs={
            "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "output_folder": str(output_folder),
        },
        runs_root=tmp_path / "runs",
        run_id="financial-advisor-test",
        llm_client=llm,
    )

    assert result["blueprint_id"] == "financial_advisor"
    artifact = result["final_artifact"]
    assert artifact["type"] == "financial_advisor_report"
    assert artifact["bank_statement_extraction"]["statement_count"] == 1
    assert artifact["bank_statement_extraction"]["totals"]["deposits"] > 0
    assert artifact["household_finance_summary"]["income_total"] > 0
    assert artifact["tax_review_packet"]["workpapers"]["draft_income_total"] > 0
    assert artifact["tax_form_ocr_capture"]["tax_form_count"] == 2
    assert artifact["tax_form_ocr_capture"]["answer_file_count"] == 2
    assert artifact["tax_form_ocr_capture"]["forms"][0]["validation_status"] == "matched_companion_answer_file"
    assert artifact["portfolio_risk_review"]["total_value"] > 0
    assert set(artifact["llm_analysis"]) >= {"cash_flow", "tax", "portfolio", "review_only"}
    assert artifact["llm_analysis"]["cash_flow"]["review_only"] is True
    assert artifact["llm_analysis"]["tax"]["review_only"] is True
    assert artifact["llm_analysis"]["portfolio"]["review_only"] is True
    assert artifact["llm_usage"]["calls"] >= 7
    assert llm.calls >= 7
    assert artifact["model_profiles_used"]["cash_flow_llm_analyst"]["llm_config"] == "primary"
    assert artifact["model_profiles_used"]["tax_llm_reviewer"]["llm_config"] == "primary"
    assert artifact["model_profiles_used"]["portfolio_llm_reviewer"]["llm_config"] == "primary"
    assert artifact["model_profiles_used"]["financial_advice_reporter"]["llm_config"] == "primary"
    assert (tmp_path / "runs" / "financial-advisor-test" / "final_artifact.json").exists()
    assert (tmp_path / "runs" / "financial-advisor-test" / "action_ledger.json").exists()
    assert (tmp_path / "runs" / "financial-advisor-test" / "artifact_quality.json").exists()
    assert (tmp_path / "runs" / "financial-advisor-test" / "run_health.json").exists()
    assert (output_folder / "result.json").exists()
    assert (output_folder / "final_artifact.json").exists()
    assert (output_folder / "financial_advisor_report.md").exists()
    assert (output_folder / "bank_statement_extraction.json").exists()
    assert (output_folder / "cash_flow_llm_review.json").exists()
    assert (output_folder / "tax_form_ocr_capture.json").exists()
    assert (output_folder / "tax_llm_review.json").exists()
    assert (output_folder / "portfolio_llm_review.json").exists()
    markdown = (output_folder / "financial_advisor_report.md").read_text(encoding="utf-8")
    assert "review-only" in markdown
    assert "## LLM Cash-Flow Review" in markdown
    assert "## LLM Tax Review" in markdown
    assert "## LLM Portfolio Review" in markdown
    assert "## Document Ingestion and OCR" in markdown
    assert artifact["document_ingestion"]["ocr_required_count"] >= 0


def test_financial_advisor_reader_routes_pdf_and_images_through_ocr_skill(monkeypatch, tmp_path):
    runner = _load_runner()
    image = tmp_path / "statement.png"
    image.write_bytes(b"synthetic-image")
    calls: list[dict[str, object]] = []

    def fake_extract(path, **kwargs):
        calls.append({"path": path, **kwargs})
        return {
            "document_type": "bank_statement",
            "text": "Bank statement\nDeposit 100.00",
            "ocr_required": False,
            "extraction_method": "llm_ocr",
            "warnings": [],
            "pages": [{"page_number": 1, "text": "Bank statement"}],
            "metadata": {"ocr_model": "LightOnOCR-2-1B"},
        }

    monkeypatch.setattr(runner, "extract_document", fake_extract)
    document = runner.read_document(image, ocr_client=object())

    assert len(calls) == 1
    assert calls[0]["path"] == image
    assert calls[0]["min_text_chars"] == 40
    assert document["kind"] == "bank_statement"
    assert document["extraction_method"] == "llm_ocr"
    assert document["ocr_required"] is False
    assert document["metadata"]["ocr_model"] == "LightOnOCR-2-1B"


def test_financial_advisor_ocr_runtime_uses_runtime_managed_skill_factory(monkeypatch):
    runner = _load_runner()

    class FakeOcrClient:
        config = type("Config", (), {"model": "hf.co/noctrex/LightOnOCR-2-1B-GGUF:Q4_K_M", "backend": "llama.cpp", "expected_accelerator": "metal"})()

    factory_calls = 0

    def factory(config):
        nonlocal factory_calls
        factory_calls += 1
        return lambda: FakeOcrClient()

    monkeypatch.setattr(runner, "docker_ocr_client_factory_from_config", factory)
    monkeypatch.setattr(runner, "extract_document", object())
    ctx = {
        "config": {"input_skills": {"llm_ocr": {"enabled": True, "install_policy": "runtime"}}},
        "payload": {},
        "llm": type("LiveLLM", (), {"provider": "docker_model_runner"})(),
    }

    client, status = runner.build_ocr_runtime(ctx)

    assert factory_calls == 1
    assert isinstance(client, FakeOcrClient)
    assert status["status"] == "ready_for_runtime_managed_first_use"
    assert status["runtime_model"].endswith("Q4_K_M")


def test_financial_advisor_actor_prompt_includes_role_contract_and_playbook_context():
    runner = _load_runner()
    llm = FakeFinancialLLM()
    config = json.loads((ROOT / "financial_advisor" / "config" / "default.json").read_text(encoding="utf-8"))

    runner.actor_review(
        config,
        llm,
        "tax_llm_reviewer",
        "Review the draft tax packet.",
        {"tax_year": 2025, "source_refs": ["sample-w2.txt"]},
        fallback={"summary": "fallback"},
        prompt_details=runner.load_prompt("tax-llm-review.md"),
        active_knowledge=runner.load_financial_knowledge(ROOT / "financial_advisor"),
    )

    assert len(llm.prompts) == 1
    system_prompt = llm.prompts[0]["system"]
    user_payload = json.loads(llm.prompts[0]["user"])
    assert "Tax LLM Reviewer" in system_prompt
    assert "Deterministic workflow outputs are authoritative" in system_prompt
    assert user_payload["role"] == "Tax LLM Reviewer"
    assert user_payload["knowledge_context"]["playbook"]["id"] == "financial_advisor_playbook"
    assert any(section["title"] == "Tax Workpapers" for section in user_payload["knowledge_context"]["sections"])
    assert "evidence_gaps" in user_payload["output_contract"]["required_fields"]


def test_financial_advisor_explicit_quick_test_can_use_deterministic_llm(tmp_path):
    runner = _load_runner()
    output_folder = tmp_path / "out"

    result = runner.run_blueprint(
        inputs={
            "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
            "output_folder": str(output_folder),
        },
        config={"execution": {"quick_test": True}},
        runs_root=tmp_path / "runs",
        run_id="financial-advisor-quick-test",
    )

    artifact = result["final_artifact"]
    assert artifact["llm_usage"]["provider"] == "fake"
    assert artifact["llm_usage"]["calls"] >= 7
    assert artifact["llm_usage"]["fallback_calls"] >= 7
    assert artifact["llm_analysis"]["review_only"] is True
    assert (output_folder / "cash_flow_llm_review.json").exists()
    assert (output_folder / "tax_llm_review.json").exists()
    assert (output_folder / "portfolio_llm_review.json").exists()


def test_financial_advisor_live_config_does_not_silently_instantiate_deterministic_llm(tmp_path, monkeypatch):
    runner = _load_runner()
    monkeypatch.setattr(runner, "get_actor_llm_client", None)
    monkeypatch.delenv("MN_BLUEPRINT_QUICK_TEST", raising=False)
    monkeypatch.delenv("MN_QUICK_TEST", raising=False)
    monkeypatch.delenv("MN_LLM_MODE", raising=False)
    monkeypatch.delenv("MN_LLM_PROVIDER", raising=False)
    monkeypatch.delenv("LITELLM_MODE", raising=False)
    monkeypatch.delenv("LITELLM_PROVIDER", raising=False)

    with pytest.raises(RuntimeError, match="shared live LLM client"):
        runner.build_context(
            inputs={
                "document_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
                "input_folder": str(ROOT / "financial_advisor" / "examples" / "sample_inputs"),
                "output_folder": str(tmp_path / "out"),
            },
            config={"llm": {"mode": "live"}, "execution": {"quick_test": False}},
            config_json=None,
            runs_root=tmp_path / "runs",
            run_id="financial-advisor-live-config",
            llm_client=None,
        )
