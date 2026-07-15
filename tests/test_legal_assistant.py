from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "legal_assistant"
RUNNER_PATH = BLUEPRINT_DIR / "payloads" / "runtime" / "runtime.py"
HEAVY_STEPS = {
    "contract_playbook_comparator",
    "legal_review_auditor",
    "legal_reporter",
}
WORKFLOW_STEPS = [
    "legal_folder_watcher",
    "legal_document_reader",
    "invoice_bill_extractor",
    "payable_field_validator",
    "contract_clause_extractor",
    "contract_playbook_comparator",
    "legal_evidence_reconciler",
    "legal_review_auditor",
    "legal_reporter",
]


def _load_runner():
    spec = importlib.util.spec_from_file_location("legal_assistant_runner", RUNNER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


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
    return module.expand_manifest_source(source, root_dir=BLUEPRINT_DIR)


class FakeLegalLLM:
    provider = "fake"
    model = "fake-legal"

    def __init__(self) -> None:
        self.calls = 0
        self.fallback_calls = 0

    def generate_json(self, *, system_prompt: str, user_prompt: str, fallback: dict):
        self.calls += 1
        response = dict(fallback)
        response["summary"] = response.get("summary") or "Fake legal review completed."
        response["provider"] = self.provider
        response["model"] = self.model
        return response


def test_legal_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v2"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["identity"]["id"] == "legal_assistant"
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == WORKFLOW_STEPS
    assert manifest["agents"]["extra_templates"] == [
        {
            "node_id": "report_sink",
            "uses": "mn-agents.control.terminal_sink@1",
            "with": {"stereotype": "terminal_report_sink"},
        }
    ]
    groups = manifest["workers"]["groups"]
    assert any(group["with"]["stereotype"] == "internal_write_worker" for group in groups)


def test_legal_model_profiles_assign_large_to_heavy_nodes():
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert config["llm"]["model"] == "default"
    assert "runtime_model" not in config["llm"]
    assert "preferred_model" not in config["llm"]
    assert "model" not in config["llm"]["configs"]["primary"]
    assert set(config["llm"]["configs"]) == {"primary"}
    for step, spec in config["llm"]["agents"].items():
        assert spec["llm_config"] == "primary", step

    assert set(manifest["workers"]["by_step"]) == HEAVY_STEPS
    assert all(item["with"]["llm_config"] == "primary" for item in manifest["workers"]["by_step"].values())


def test_legal_source_manifest_expands_with_terminal_sink():
    source = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}
    assert "report_sink" in node_ids
    assert "legal_reporter" in node_ids
    assert any(
        edge["from_node"] == "legal_reporter" and edge["to_node"] == "report_sink"
        for edge in expanded["agents"]["edges"]
    )
    rendered_reporter = next(node for node in expanded["agents"]["nodes"] if node["node_id"] == "legal_reporter")
    assert rendered_reporter["config"]["llm_config"] == "primary"
    assert rendered_reporter["config"]["environment"]["MN_LLM_CONFIG"] == "primary"
    assert expanded["runtime"]["resources"]["gpu"] == {"min_count": 0}


def test_legal_runner_resolves_config_from_docker_worker_attempt_root(monkeypatch, tmp_path):
    runner = _load_runner()
    attempt_root = tmp_path / "runs" / "legal_folder_watcher" / "i1-a1-23108"
    script_path = attempt_root / "runtime" / "runtime.py"
    config_path = attempt_root / "config" / "default.json"
    script_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        json.dumps(
            {
                "identity": {"blueprint_id": "legal_assistant"},
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
    assert runner.load_resolved_config()["identity"]["blueprint_id"] == "legal_assistant"


def test_legal_runner_selects_cluster_medium_or_small_fallback(monkeypatch):
    runner = _load_runner()
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))

    monkeypatch.setenv(
        "MN_MODEL_ENDPOINTS_JSON",
        json.dumps(
            {
                "nemotron3": {
                    "model": "docker.io/ai/nemotron3:latest",
                    "runtime_model": "docker.io/ai/nemotron3:latest",
                    "api_base": "http://mn-litellm-proxy:4000/v1",
                    "provider": "docker_model_runner",
                    "node": "mirror_neuron@gpu-node",
                }
            }
        ),
    )
    medium = runner.select_default_model(config)
    assert medium["selected_model"] == "medium"
    assert medium["runtime_model"] == "docker.io/ai/nemotron3:latest"
    assert medium["node"] == "mirror_neuron@gpu-node"

    monkeypatch.setenv(
        "MN_MODEL_ENDPOINTS_JSON",
        json.dumps(
            {
                "small": {
                    "model": "docker.io/ai/gemma4:E2B",
                    "runtime_model": "docker.io/ai/gemma4:E2B",
                    "provider": "docker_model_runner",
                }
            }
        ),
    )
    small = runner.select_default_model(config)
    assert small["selected_model"] == "small"
    assert small["model"] == "docker.io/ai/gemma4:E2B"


def test_legal_runner_uses_effective_profile_for_advertised_runtime():
    runner = _load_runner()
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))

    small_selection = {"selected_model": "small", "model": "docker.io/ai/gemma4:E2B"}
    small_profiles = runner.model_profiles_used(config, small_selection)
    assert small_profiles["contract_playbook_comparator"] == {"llm_config": "primary", "model": "default"}
    assert runner.llm_profile_config(config, "contract_playbook_comparator", small_selection)["strict_json"] is False

    medium_selection = {"selected_model": "medium", "model": "docker.io/ai/nemotron3:latest"}
    medium_profiles = runner.model_profiles_used(config, medium_selection)
    assert medium_profiles["contract_playbook_comparator"] == {"llm_config": "primary", "model": "default"}
    assert runner.llm_profile_config(config, "contract_playbook_comparator", medium_selection)["strict_json"] is False


def test_legal_runner_resolves_job_output_dir_for_containerized_runs(monkeypatch, tmp_path):
    runner = _load_runner()
    output_folder = tmp_path / "shared" / "outputs" / "legal"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output_folder))

    payload = {"output_folder": "~/Downloads/legal_assistant"}
    resolved_config = {"outputs": {"folder_path": str(tmp_path / "configured")}}

    assert runner.resolve_output_folder(payload, resolved_config, inputs={}) == output_folder


def test_legal_runner_keeps_explicit_output_dir_for_local_runs(monkeypatch, tmp_path):
    runner = _load_runner()
    explicit_output = tmp_path / "explicit"
    monkeypatch.delenv("MN_JOB_OUTPUT_DIR", raising=False)

    payload = {"output_folder": "~/Downloads/legal_assistant"}
    resolved_config = {"outputs": {"folder_path": str(tmp_path / "configured")}}

    assert runner.resolve_output_folder(payload, resolved_config, inputs={"output_folder": str(explicit_output)}) == explicit_output


def test_legal_smoke_run_writes_merged_artifacts(tmp_path, monkeypatch):
    runner = _load_runner()
    llm = FakeLegalLLM()
    output_folder = tmp_path / "out"
    monkeypatch.setenv("MN_JOB_OUTPUT_DIR", str(output_folder))
    result = runner.run_blueprint(
        inputs={
            "document_folder": str(BLUEPRINT_DIR / "examples" / "sample_inputs"),
            "input_folder": str(BLUEPRINT_DIR / "examples" / "sample_inputs"),
        },
        runs_root=tmp_path / "runs",
        run_id="legal-test",
        llm_client=llm,
    )

    assert result["blueprint_id"] == "legal_assistant"
    artifact = result["final_artifact"]
    assert artifact["type"] == "legal_assistant_report"
    assert artifact["invoice_bill_extraction"]["invoice_count"] == 1
    assert artifact["invoice_bill_extraction"]["totals"]["total_amount"] == 1842.66
    assert artifact["contract_clause_review"]["contract_count"] >= 1
    assert artifact["contract_clause_review"]["clause_count"] >= 5
    assert artifact["model_profiles_used"]["legal_reporter"]["llm_config"] == "primary"
    assert set(artifact["actor_findings"]) == {
        "invoice_bill_extractor",
        "payable_field_validator",
        "contract_clause_extractor",
        "contract_playbook_comparator",
        "legal_evidence_reconciler",
        "legal_review_auditor",
        "legal_reporter",
    }
    assert (tmp_path / "runs" / "legal-test" / "final_artifact.json").exists()
    assert (output_folder / "legal_assistant_report.md").exists()
    assert (output_folder / "legal_deep_review.json").exists()
    assert (output_folder / "invoice_bill_extraction.json").exists()
    assert (output_folder / "contract_clause_review.json").exists()


def test_legal_sample_packet_includes_real_public_contract_fixture():
    sample_dir = BLUEPRINT_DIR / "examples" / "sample_inputs"
    sample_manifest = json.loads((sample_dir / "SAMPLE_DATASET_MANIFEST.json").read_text(encoding="utf-8"))

    real_fixture = next(item for item in sample_manifest["files"] if item["type"] == "real_public_contract_terms_pdf")
    assert (sample_dir / real_fixture["path"]).exists()
    assert real_fixture["source_url"].startswith("https://www.acquisition.gov/")
