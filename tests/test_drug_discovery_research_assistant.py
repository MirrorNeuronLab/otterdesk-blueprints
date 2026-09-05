from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import threading
import types
import urllib.request
from pathlib import Path

import pytest
from blueprint_modernization_support import (
    assert_modular_payload,
    assert_registry_handlers_import,
)
from mn_sdk import apply_manifest_config_bindings
from mn_sdk.blueprint_runtime import load_blueprint_config
from mn_sdk.blueprints import blueprint_definition, read_blueprint
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "drug_discovery_research_assistant"
WORKSPACE = companion_workspace(ROOT)
STEP_SCRIPTS = {
    "target_discovery": "scripts/stage_a.py",
    "structure_generation": "scripts/stage_b.py",
    "candidate_generation": "scripts/run_continuous_service.py",
    "binding_evaluation": "scripts/stage_d.py",
    "ranking_reporting": "scripts/stage_e.py",
}
STEP_AGENTS = {
    "target_discovery": "target_biology_researcher",
    "structure_generation": "structure_modeler",
    "candidate_generation": "discovery_service_operator",
    "binding_evaluation": "binding_evidence_reviewer",
    "ranking_reporting": "discovery_packet_writer",
}


def _expand_source_manifest(source: dict) -> dict:
    from mn_sdk import expand_manifest_source

    return expand_manifest_source(source, root_dir=BLUEPRINT_DIR)


def test_drug_discovery_manifest_uses_source_format_and_shared_blocks():
    manifest = blueprint_definition(read_blueprint(BLUEPRINT_DIR / "manifest.json"))

    assert manifest["apiVersion"] == "mn.workflow/v1"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["type"] == "batch"
    assert manifest["identity"]["id"] == "drug_discovery_research_assistant"
    assert manifest["skill_dependencies"] == [
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-use-generic-model-skill",
            "version": "1.3.22",
        },
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-job-response-skill",
            "version": "1.3.22",
        },
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-mcp-client-skill",
            "version": "1.3.22",
        },
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-rag-skill",
            "version": "1.3.22",
        },
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-web-ui-skill",
            "version": "1.3.22",
        },
    ]
    assert (
        manifest["config"]["data"]["interfaces"]["input_contract"]
        == manifest["contracts"]["inputs"]
    )
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert read_blueprint(BLUEPRINT_DIR).manifest["version"] == "1.0.0"
    assert "entrypoints" not in manifest["agents"]
    assert manifest["agents"]["auxiliary_entrypoints"] == ["drug_discovery_web_ui"]
    [web_ui_node] = manifest["agents"]["extra_nodes"]
    assert web_ui_node["node_id"] == "drug_discovery_web_ui"
    assert web_ui_node["type"] == "stream"
    assert web_ui_node["config"]["runner_module"] == "MirrorNeuron.Runner.HostLocal"
    assert web_ui_node["config"]["command"] == [
        "python3.11",
        "services/drug_discovery_web_ui.py",
    ]
    assert web_ui_node["services"][0]["name"] == "drug-discovery-progress"
    assert web_ui_node["services"][0]["checks"][0]["path"] == "/healthz"
    assert manifest["metadata"]["web_ui"]["source_of_truth"] == "workflow.steps"
    assert manifest["metadata"]["web_ui"]["registration"]["scope"] == "job"
    assert manifest["metadata"]["web_ui"]["adapter"] == "external-url"
    assert manifest["metadata"]["web_ui"]["kind"] == "service"
    assert "external_url" in manifest["metadata"]["interfaces"]["web_ui_adapters"]
    assert manifest["metadata"]["web_ui"]["molecule_artifacts"] == [
        "leading_candidate.json",
        "leading_candidate.svg",
    ]
    output_paths = {
        artifact["path"] for artifact in manifest["contracts"]["outputs"]["artifacts"]
    }
    assert {"leading_candidate.json", "leading_candidate.svg"} <= output_paths
    assert [step["id"] for step in manifest["workflow"]["steps"]] == list(STEP_SCRIPTS)
    assert manifest["agents"].get("extra_templates", []) == []
    assert manifest["defaults"]["worker"]["uses"] == "mn-agents.worker.python_host@1"
    assert "python_environment" not in manifest["defaults"]["worker"]["with"]
    assert (
        "blueprint_host_worker" in manifest["defaults"]["worker"]["with"]["stereotype"]
    )
    assert {
        entry["source"]
        for entry in manifest["defaults"]["worker"]["with"]["upload_paths"]
    } == {
        "service",
        "domain",
        "biotarget",
    }
    for script in STEP_SCRIPTS.values():
        assert (BLUEPRINT_DIR / "payloads" / "service" / script).is_file(), script
    assert (BLUEPRINT_DIR / "payloads" / "prompts" / "scientific-review.md").is_file()
    assert manifest["service"]["run_until"] == "one_cycle"
    assert manifest["cluster_distribution"]["enabled"] is False
    assert (
        manifest["cluster_distribution"]["collaboration"]["mode"]
        == "cross_box_fanout_fanin"
    )
    assert "runtime" not in manifest
    assert manifest["requirements"]["gpu"] == {
        "driver": "cuda",
        "enforcement": "hard",
        "memory_operator": ">=",
        "min_count": 1,
        "min_memory_mb": 49152,
        "vendor": "nvidia",
    }
    [gpu_worker] = manifest["workers"]["groups"]
    assert set(gpu_worker["steps"]) == {
        "target_discovery",
        "structure_generation",
        "candidate_generation",
        "binding_evaluation",
        "ranking_reporting",
    }
    assert gpu_worker["uses"] == "mn-agents.worker.python_docker@1"
    assert gpu_worker["with"]["gpus"] == "all"
    assert gpu_worker["with"]["docker_worker_image"] == "docker_worker"
    assert (
        gpu_worker["with"]["image"]
        == "mirror-neuron/drug-discovery-research-assistant:drugclip-gnina"
    )

    assert {step["id"] for step in manifest["workflow"]["steps"]} == set(STEP_SCRIPTS)
    assert set(manifest["agents"]["registry"]) == set(STEP_AGENTS.values())
    for step in STEP_SCRIPTS:
        assert (
            manifest["workflow"]["steps"][
                [item["id"] for item in manifest["workflow"]["steps"]].index(step)
            ]["run"]["definition"]
            == f"steps.{step}"
        )
    candidate_step = next(
        item
        for item in manifest["workflow"]["steps"]
        if item["id"] == "candidate_generation"
    )
    assert candidate_step["control"] == {
        "failure_policy": "fail_workflow",
        "required": True,
        "retry": {
            "backoff_multiplier": 2,
            "backoff_seconds": 1,
            "jitter": 0,
            "max_attempts": 1,
        },
        "timeout_seconds": 86400,
    }


def test_drug_discovery_uses_logical_default_llm_route():
    default_config = read_blueprint(BLUEPRINT_DIR).document("config")
    config = load_blueprint_config(BLUEPRINT_DIR)

    assert config["mode"] == "live"
    assert config["execution"]["fake_science_adapters"] is False
    assert config["execution"]["mode"] == "native_local"
    assert config["cluster_distribution"]["enabled"] is False
    assert config["service"]["run_until"] == "one_cycle"
    assert config["service"]["max_cycles"] == 1
    assert config["service"]["candidate_count"] == 5
    assert config["service"]["candidate_pool_size"] == 800
    assert config["service"]["drugclip_scoring_batch_size"] == 64
    assert [step["id"] for step in config["web_ui"]["workflow_steps"]] == list(
        STEP_SCRIPTS
    )
    assert [step["id"] for step in config["service"]["cycle_steps"]] == [
        "generate_candidates",
        "fold_targets",
        "screen_with_drugclip",
        "simulate_candidates",
        "publish_cycle_report",
    ]
    assert default_config["web_ui"]["renderer"] == "external-url"
    assert default_config["web_ui"]["molecule_preview"] == {
        "enabled": True,
        "width": 720,
        "height": 420,
    }
    assert default_config["web_ui"]["service"]["port"] == 61020
    assert config["resources"]["gpu"] == {
        "min_count": 1,
        "vendor": "nvidia",
        "driver": "cuda",
        "min_memory_mb": 49152,
        "memory_operator": ">=",
        "enforcement": "hard",
    }
    assert config["outputs"]["folder_path"] == "~/Downloads/{job_name}"
    assert config["llm"]["provider"] == "docker_model_runner"
    assert config["llm"]["model"] == "default"
    assert "runtime_model" not in config["llm"]
    assert "live_model_profile" not in config["llm"]
    assert "preferred_model" not in config["llm"]
    assert config["llm"]["configs"]["primary"]["provider"] == "docker_model_runner"
    assert config["llm"]["configs"]["primary"]["api_base"] == "auto"
    assert "model" not in config["llm"]["configs"]["primary"]
    assert "runtime_model" not in config["llm"]["configs"]["primary"]
    assert set(config["llm"]["configs"]) == {"primary"}
    assert "small_model_profile" not in config["llm"]
    assert "large_model_profile" not in config["llm"]
    assert {spec["llm_config"] for spec in config["llm"]["agents"].values()} == {
        "primary"
    }
    assert "llm" not in default_config
    assert "knowledge_rag" not in default_config
    assert "resources" not in default_config
    assert "agentic_research" not in default_config
    assert "runtime_model_key" not in config["drugclip"]
    assert config["drugclip"]["model_ref"] == "hf.co/homerquan/DrugClip"
    assert (
        config["drugclip"]["generic_model"]["model_ref"]
        == "https://huggingface.co/homerquan/DrugClip"
    )
    assert config["drugclip"]["generic_model"]["runtime"] == "native_checkpoint"
    assert (
        config["drugclip"]["generic_model"]["validator"]
        == "mirrorneuron-use-generic-model-skill"
    )
    assert config["drugclip"]["generic_model"]["shared_model_catalog"] is False
    assert config["drugclip"]["checkpoint_filename"] == "best.ckpt"
    assert config["drugclip"]["source_repository"] == "@/payloads"
    assert config["biotarget"]["source_dir"] == "@/payloads"
    assert config["python_dependencies"]["requirements"] == "requirements.txt"
    requirements = (BLUEPRINT_DIR / "payloads" / "requirements.txt").read_text(
        encoding="utf-8"
    )
    for package in (
        "drugclip>=0.1.2",
        "torch>=2.12,<2.13",
        "torch_geometric>=2.3",
        "huggingface_hub",
        "rdkit",
        "requests",
    ):
        assert package in requirements
    for adapter_name in ("candidate_generator", "folding", "drugclip", "simulation"):
        assert config[adapter_name]["command"][0] == "python"
        assert config[adapter_name]["command"][1] == "scripts/biotarget_adapter.py"


def test_drug_discovery_source_manifest_expands_with_native_service_script():
    source = blueprint_definition(read_blueprint(BLUEPRINT_DIR / "manifest.json"))
    expanded = _expand_source_manifest(source)

    assert expanded["type"] == "batch"
    assert expanded["job_name"] == "drug-discovery-research-assistant"
    assert expanded["agents"]["entrypoints"] == [
        "drug_discovery_web_ui",
        "target_discovery__start",
    ]
    node_by_id = {node["node_id"]: node for node in expanded["agents"]["nodes"]}
    step_nodes = {
        node_id: node
        for node_id, node in node_by_id.items()
        if node_id.endswith(tuple(f"__{agent_id}" for agent_id in STEP_AGENTS.values()))
    }
    assert {node_id.split("__", 1)[0] for node_id in step_nodes} == set(STEP_SCRIPTS)
    for step in STEP_SCRIPTS:
        config = step_nodes[f"{step}__{STEP_AGENTS[step]}"]["config"]
        assert config["command"] == ["python3", "-m", "mn_sdk.step_runtime"]
        assert config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
        assert "python_environment" not in config
        assert config["gpus"] == "all"
        assert config["docker_worker_image"] == "docker_worker"
        assert (
            config["image"]
            == "mirror-neuron/drug-discovery-research-assistant:drugclip-gnina"
        )
    assert node_by_id["workflow__terminal"]["config"]["complete_run"] is True
    assert expanded["workflow"]["steps"]
    ui_node = node_by_id["drug_discovery_web_ui"]
    assert ui_node["config"]["runner_module"] == "MirrorNeuron.Runner.HostLocal"
    assert ui_node["services"][0]["name"] == "drug-discovery-progress"
    assert expanded["runtime"]["resources"]["gpu"] == {
        "driver": "cuda",
        "enforcement": "hard",
        "memory_operator": ">=",
        "min_count": 1,
        "min_memory_mb": 49152,
        "vendor": "nvidia",
    }


def test_drug_discovery_stage_environment_propagates_biotarget_source():
    stages = (BLUEPRINT_DIR / "payloads" / "domain" / "native_stages.py").read_text(
        encoding="utf-8"
    )
    assert 'environment["BIOTARGET_SOURCE_DIR"] = str(bundled_source)' in stages


def test_drug_discovery_bundles_biotarget_and_prefers_it_at_runtime():
    assert (BLUEPRINT_DIR / "payloads" / "biotarget" / "pipeline.py").is_file()
    adapter = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "biotarget_adapter.py"
    ).read_text(encoding="utf-8")
    assert 'bundled / "biotarget" / "pipeline.py"' in adapter
    assert "configured = os.environ" not in adapter
    assert "normalize_model_reference" in adapter
    assert "prepare_model(" not in adapter
    assert "drugclip_scoring_batch_size" in adapter
    assert "requires an NVIDIA CUDA PyTorch runtime" in adapter
    service = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    ).read_text(encoding="utf-8")
    assert '"candidates": candidates' in service
    assert (
        "DrugClip batch adapter returned incomplete target-candidate scores." in service
    )
    stages = (BLUEPRINT_DIR / "payloads" / "domain" / "native_stages.py").read_text(
        encoding="utf-8"
    )
    assert 'capture_output = script != "run_continuous_service.py"' in stages
    continuous_service = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    ).read_text(encoding="utf-8")
    assert "stdout (tail)" in continuous_service
    stage_a = (
        BLUEPRINT_DIR / "payloads" / "biotarget" / "stages" / "stage_a_discovery.py"
    ).read_text(encoding="utf-8")
    stage_d = (
        BLUEPRINT_DIR / "payloads" / "biotarget" / "stages" / "stage_d_evaluation.py"
    ).read_text(encoding="utf-8")
    assert "_mock_targets" not in stage_a
    assert "surrogate docking" not in stage_d
    assert 'shutil.which("gnina")' in stage_d
    assert '"docker",' not in stage_d
    assert "requires_gnina_cpu_emulation" not in stage_d
    assert "torch.matmul(tox_emb, all_graph_embs.T).reshape(-1)" in stage_d
    assert "normalize_01(raw_tox_scores).reshape(-1)" in stage_d
    dockerfile = (
        BLUEPRINT_DIR / "payloads" / "docker_worker" / "Dockerfile"
    ).read_text(encoding="utf-8")
    assert "nvidia/cuda:13.0.0-cudnn-devel-ubuntu24.04" in dockerfile
    assert "GNINA_VERSION=v1.3.2" in dockerfile
    assert "GNINA v1.3.2 sets CMAKE_CXX_STANDARD to 17" in dockerfile
    assert "CMAKE_CUDA_ARCHITECTURES=121" in dockerfile
    assert "python3 -m venv /opt/mn-venv" in dockerfile
    assert "/opt/mn-venv/lib/python3.12/site-packages/torch/lib" in dockerfile


def test_drug_discovery_payload_is_modular_and_handlers_resolve():
    assert_modular_payload("drug_discovery_research_assistant")
    assert_registry_handlers_import("drug_discovery_research_assistant")


def test_continuous_service_fake_mode_writes_parallel_cycle_artifacts(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config = {
        "mode": "mock",
        "execution": {"fake_science_adapters": True},
        "service": {
            "max_cycles": 1,
            "cycle_interval_seconds": 0.1,
            "simulation_top_k": 2,
            "parallelism": {
                "folding_workers": 2,
                "drugclip_workers": 2,
                "simulation_workers": 2,
            },
        },
        "cluster_distribution": {"enabled": False, "worker_pools": {}},
        "inputs": {"payload": {"targets": [{"protein_id": "P56817", "gene": "BACE1"}]}},
    }
    result = module.run_service(config, tmp_path)

    assert result["status"] == "stopped"
    assert result["completed_cycles"] == 1
    cycle = tmp_path / "cycles" / "cycle-000000"
    for name in (
        "generated_candidates.json",
        "folding_results.json",
        "drugclip_screening.json",
        "simulation_results.json",
        "cycle_report.json",
    ):
        assert (cycle / name).exists(), name
    report = json.loads((cycle / "cycle_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "fake_smoke_test"
    assert report["simulation_count"] == 5
    assert len({row["candidate"]["smiles"] for row in report["top_candidates"]}) == 5
    assert report["molecule_preview"]["status"] == "ready"
    assert report["molecule_preview"]["renderer"] in {
        "rdkit_2d_svg",
        "synthetic_smoke_test",
    }
    preview = json.loads((cycle / "leading_candidate.json").read_text(encoding="utf-8"))
    assert preview["schema_version"] == "mn.blueprint.leading_candidate_preview.v1"
    assert preview["status"] == "ready"
    svg = (cycle / "leading_candidate.svg").read_text(encoding="utf-8")
    assert "<svg" in svg
    progress = json.loads(
        (tmp_path / "cycle_progress.json").read_text(encoding="utf-8")
    )
    assert progress["status"] == "complete"
    assert progress["mode"] == "fake_smoke_test"
    assert progress["active_step"] is None
    assert [step["status"] for step in progress["steps"]] == ["Complete"] * 5
    assert progress["counts"] == {
        "targets": 1,
        "candidates": 5,
        "screens": 5,
        "simulations": 5,
    }


def test_five_candidate_policy_rejects_duplicate_shortfall():
    module = _load_drug_discovery_domain_module("candidates")
    with pytest.raises(RuntimeError, match="five distinct"):
        module.five_distinct_candidates([{"smiles": "C"}] * 5, synthetic=True)
    candidates = [{"smiles": value} for value in ("C", "C", "CC", "CCC", "CO", "CN")]
    assert len(module.five_distinct_candidates(candidates, synthetic=True)) == 5


def test_one_cycle_handoff_produces_five_reviewed_candidates(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "discovery_one_cycle_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.run_service(
        {
            "mode": "mock",
            "service": {"max_cycles": None},
            "inputs": {
                "payload": {
                    "targets": [
                        {"protein_id": "P1"},
                        {"protein_id": "P2"},
                    ]
                }
            },
        },
        tmp_path,
    )
    assert result["completed_cycles"] == 1
    payload = {"reports": result["reports"]}
    message = tmp_path / "message.json"
    for script in ("stage_d.py", "stage_e.py"):
        message.write_text(json.dumps({"body": payload}))
        process = subprocess.run(
            [sys.executable, str(service_path.parent / script)],
            env={
                **os.environ,
                "MN_MESSAGE_FILE": str(message),
                "MN_RUN_DIR": str(tmp_path),
            },
            text=True,
            capture_output=True,
            check=True,
        )
        payload = json.loads(process.stdout.splitlines()[-1])
    report = payload["review_report"]
    assert report["candidate_count"] == 5
    assert len({row["candidate"]["smiles"] for row in report["ranked_candidates"]}) == 5
    assert (tmp_path / "discovery_service_review.json").is_file()


def test_continuous_service_publishes_user_facing_candidates(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_output_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output_folder = tmp_path / "Downloads" / "drug_discovery_research_assistant"
    config = {
        "mode": "mock",
        "execution": {"fake_science_adapters": True},
        "service": {
            "max_cycles": 1,
            "simulation_top_k": 1,
            "parallelism": {
                "folding_workers": 1,
                "drugclip_workers": 1,
                "simulation_workers": 1,
            },
        },
        "cluster_distribution": {"enabled": False},
        "inputs": {
            "payload": {
                "output_folder": str(output_folder),
                "targets": [{"protein_id": "P56817", "gene": "BACE1"}],
            }
        },
    }

    module.run_service(config, tmp_path / "run")

    candidates = json.loads(
        (output_folder / "candidates.json").read_text(encoding="utf-8")
    )
    assert candidates["schema_version"] == "mn.blueprint.staged_candidates.v1"
    assert candidates["candidate_count"] == len(candidates["candidates"]) > 0
    assert (output_folder / "latest_cycle_report.json").exists()
    status = json.loads(
        (output_folder / "service_status.json").read_text(encoding="utf-8")
    )
    assert status["status"] == "stopped"
    assert status["completed_cycles"] == 1
    assert (output_folder / "cycle_progress.json").exists()
    molecule = json.loads(
        (output_folder / "leading_candidate.json").read_text(encoding="utf-8")
    )
    assert molecule["status"] == "ready"
    assert molecule["candidate_id"]
    assert molecule["smiles"]
    assert (output_folder / "leading_candidate.svg").exists()


def _load_drug_discovery_web_ui():
    module_path = BLUEPRINT_DIR / "payloads" / "services" / "drug_discovery_web_ui.py"
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_web_ui_test", module_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_drug_discovery_domain_module(name: str):
    package_name = "drug_discovery_domain_test"
    domain_dir = BLUEPRINT_DIR / "payloads" / "domain"
    package = types.ModuleType(package_name)
    package.__path__ = [str(domain_dir)]
    sys.modules[package_name] = package
    module_name = f"{package_name}.{name}"
    spec = importlib.util.spec_from_file_location(
        module_name, domain_dir / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def test_drug_discovery_web_ui_shows_workflow_and_cycle_steps_clearly():
    module = _load_drug_discovery_web_ui()
    html = module.dashboard_html()

    assert 'id="molecule-image"' in html
    assert "Leading candidate" in html
    assert "Workflow steps" in html
    assert "Current discovery cycle" in html
    assert "DrugCLIP screens" in html
    assert "Scientific review boundary" in html
    assert "fetch('/ui/state'" in html


def test_drug_discovery_web_ui_projects_durable_progress_without_candidates(
    tmp_path,
):
    module = _load_drug_discovery_web_ui()
    config = load_blueprint_config(BLUEPRINT_DIR)
    workflow_state = tmp_path / "workflow_state"
    workflow_state.mkdir()
    (workflow_state / "drug_discovery_state.json").write_text(
        json.dumps(
            {
                "targets": [{"gene": "BACE1"}],
                "structures": [{"gene": "BACE1", "path": "/private/receptor.pdb"}],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "service_state.json").write_text(
        json.dumps(
            {
                "status": "running",
                "completed_cycles": 2,
                "last_report": {
                    "candidate_count": 160,
                    "screen_count": 160,
                    "simulation_count": 16,
                    "top_candidates": [{"smiles": "CONFIDENTIAL-SMILES"}],
                },
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "cycle_progress.json").write_text(
        json.dumps(
            {
                "cycle_id": 2,
                "status": "running",
                "active_step": "screen_with_drugclip",
                "updated_at": "2026-09-01T12:00:00Z",
                "counts": {
                    "targets": 1,
                    "candidates": 160,
                    "screens": 64,
                    "simulations": 0,
                },
                "steps": [
                    {
                        "id": step["id"],
                        "label": "Artifact label must not override the manifest",
                        "status": "Complete"
                        if index < 2
                        else "Running"
                        if index == 2
                        else "Waiting",
                    }
                    for index, step in enumerate(config["service"]["cycle_steps"])
                ],
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "events.jsonl").write_text(
        json.dumps(
            {
                "type": "workflow_step_started",
                "step_id": "candidate_generation",
                "payload": {"summary": "CONFIDENTIAL TARGET TEXT"},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    service = module.DrugDiscoveryWebUIService(
        run_id="run-3", run_dir=tmp_path, config=config
    )
    state = service.ui_state()

    assert state["metrics"]["Step 1 — Target Discovery"] == "Complete"
    assert state["metrics"]["Step 2 — Structure Generation"] == "Complete"
    assert state["metrics"]["Step 3 — Discover Five Candidates"] == "Running"
    assert state["metrics"]["Cycle — Screen with DrugCLIP"] == "Running"
    assert state["metrics"]["Current cycle"] == 3
    assert state["metrics"]["DrugCLIP screens"] == 64
    assert "CONFIDENTIAL-SMILES" not in json.dumps(state)
    assert "CONFIDENTIAL TARGET TEXT" not in json.dumps(state)
    assert "/private/receptor.pdb" not in json.dumps(state)
    assert state["molecule"] == {"status": "waiting", "cycle": 1}


def test_drug_discovery_web_ui_projects_only_the_leading_molecule(tmp_path):
    module = _load_drug_discovery_web_ui()
    config = load_blueprint_config(BLUEPRINT_DIR)
    (tmp_path / "leading_candidate.json").write_text(
        json.dumps(
            {
                "status": "ready",
                "cycle_id": 4,
                "candidate_id": "candidate-17",
                "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
                "renderer": "rdkit_2d_svg",
                "drugclip_score": 0.92,
                "simulation_stability": 0.81,
                "gnina_affinity": -8.7,
                "toxicity_penalty": 0.12,
                "private_structure_path": "/private/receptor.pdb",
                "candidate_pool": [{"candidate_id": "do-not-project"}],
            }
        ),
        encoding="utf-8",
    )
    service = module.DrugDiscoveryWebUIService(
        run_id="run-molecule", run_dir=tmp_path, config=config
    )

    state = service.ui_state()

    assert state["molecule"] == {
        "status": "ready",
        "cycle": 5,
        "candidate_id": "candidate-17",
        "smiles": "CC(=O)OC1=CC=CC=C1C(=O)O",
        "renderer": "rdkit_2d_svg",
        "image_url": "/artifacts/leading_candidate.svg?cycle=4",
        "drugclip_score": 0.92,
        "simulation_stability": 0.81,
        "gnina_affinity": -8.7,
        "toxicity_penalty": 0.12,
    }
    assert "/private/receptor.pdb" not in json.dumps(state)
    assert "do-not-project" not in json.dumps(state)


def test_drug_discovery_web_ui_serves_dashboard_state_and_svg(tmp_path):
    module = _load_drug_discovery_web_ui()
    config = load_blueprint_config(BLUEPRINT_DIR)
    (tmp_path / "leading_candidate.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"><title>Candidate</title></svg>',
        encoding="utf-8",
    )
    service = module.DrugDiscoveryWebUIService(
        run_id="run-http", run_dir=tmp_path, config=config
    )
    server = module.DrugDiscoveryWebUIServer(service, host="127.0.0.1", port=0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    _host, port = server.address

    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=2) as response:
            assert response.status == 200
            assert b"Leading candidate" in response.read()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/ui/state", timeout=2
        ) as response:
            state = json.loads(response.read())
            assert state["metrics"]["Run"] == "run-http"
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/artifacts/leading_candidate.svg",
            timeout=2,
        ) as response:
            assert response.headers.get_content_type() == "image/svg+xml"
            assert b"<title>Candidate</title>" in response.read()
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/healthz", timeout=2
        ) as response:
            assert json.loads(response.read())["status"] == "ok"
    finally:
        server.stop()
        thread.join(timeout=2)


def test_drug_discovery_web_ui_requires_direct_job_data_directory(
    tmp_path, monkeypatch
):
    module = _load_drug_discovery_web_ui()
    job_dir = tmp_path / "job-1"
    monkeypatch.setenv("MN_JOB_DATA_DIR", str(job_dir))
    assert module.configured_job_data_dir("job-1") == job_dir.resolve()
    try:
        module.configured_job_data_dir("job-2")
    except RuntimeError as error:
        assert "direct directory" in str(error)
    else:  # pragma: no cover - guards job isolation
        raise AssertionError("web UI accepted another job's data directory")


def test_drug_discovery_web_ui_config_updates_expanded_service_contract():
    source = blueprint_definition(read_blueprint(BLUEPRINT_DIR / "manifest.json"))
    manifest = _expand_source_manifest(source)
    config = load_blueprint_config(BLUEPRINT_DIR)
    config["web_ui"]["service"]["port"] = 61027

    apply_manifest_config_bindings(manifest, config)

    node = next(
        item
        for item in manifest["agents"]["nodes"]
        if item["node_id"] == "drug_discovery_web_ui"
    )
    assert node["resources"]["ports"][0]["port"] == 61027
    assert node["services"][0]["port"] == 61027


def test_drug_discovery_reporting_writes_the_declared_final_contract(
    tmp_path, monkeypatch
):
    module = _load_drug_discovery_domain_module("reporting")
    stored_state = {}
    monkeypatch.setattr(module, "read_discovery_state", lambda _ctx: {})
    monkeypatch.setattr(
        module,
        "run_stage_script",
        lambda *_args, **_kwargs: {
            "review_report": {
                "candidate_count": 2,
                "ranked_candidates": [{"candidate_id": "candidate-1"}],
                "recommendation": "review_required",
            }
        },
    )
    monkeypatch.setattr(
        module,
        "write_discovery_state",
        lambda _ctx, state: stored_state.update(state),
    )
    run_dir = tmp_path / "run"
    output_dir = tmp_path / "output"
    run_dir.mkdir()

    result = module.publish_ranking(
        {
            "run_dir": str(run_dir),
            "output_folder": str(output_dir),
            "config": {},
        }
    )

    artifact = result["final_artifact"]
    manifest = blueprint_definition(read_blueprint(BLUEPRINT_DIR / "manifest.json"))
    required = manifest["contracts"]["outputs"]["primary"]["required_fields"]
    assert set(required) <= set(artifact)
    assert artifact["confidence"] == 0.25
    assert artifact["evidence"][0]["candidate_count"] == 2
    assert {"inputs.json", "events.jsonl", "result.json"} <= set(
        artifact["source_refs"]
    )
    assert json.loads((run_dir / "final_artifact.json").read_text()) == artifact
    assert json.loads((output_dir / "final_artifact.json").read_text()) == artifact
    assert stored_state["final_report"] == artifact


def test_discovery_runs_once_even_with_legacy_unlimited_config(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_loop_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    calls = []

    def fake_cycle(config, run_dir, cycle_id):
        calls.append(cycle_id)
        report = {
            "cycle_id": cycle_id,
            "top_candidates": [{"candidate": {"smiles": "C"}}],
        }
        if len(calls) == 2:
            (run_dir / "STOP").touch()
        return report

    module.run_cycle = fake_cycle
    result = module.run_service(
        {
            "mode": "mock",
            "service": {
                "max_cycles": None,
                "cycle_interval_seconds": 0.1,
                "stop_file": "${MN_RUN_DIR}/STOP",
            },
            "cluster_distribution": {"enabled": False},
        },
        tmp_path,
    )

    assert calls == [0]
    assert result["completed_cycles"] == 1
    assert result["stop_reason"] == "max_cycles"


def test_continuous_service_uses_unique_work_directories_for_parallel_jobs(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_paths_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    first = module.job_artifact_dir(tmp_path, "drugclip", "P12345", "candidate-1")
    second = module.job_artifact_dir(tmp_path, "drugclip", "P67890", "candidate-1")
    assert first != second
    assert first.parent == second.parent == tmp_path / "drugclip"


def test_biotarget_adapter_makes_folded_structure_path_absolute(tmp_path):
    adapter_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "biotarget_adapter.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_biotarget_adapter_path_test", adapter_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    receptor = tmp_path / "runs" / "structures" / "BACE1_P56817.pdb"
    receptor.parent.mkdir(parents=True)
    receptor.write_text("HEADER    TEST STRUCTURE\nEND\n", encoding="utf-8")

    result = module.absolute_structure_result(
        {"gene": "BACE1", "path": "./runs/structures/BACE1_P56817.pdb"},
        tmp_path,
    )

    assert result["path"] == str(receptor.resolve())


def test_biotarget_stage_b_uses_stable_pdb_url_after_api_failure(tmp_path, monkeypatch):
    stage_path = (
        BLUEPRINT_DIR / "payloads" / "biotarget" / "stages" / "stage_b_structure.py"
    )

    class RequestException(Exception):
        pass

    class HTTPError(RequestException):
        pass

    monkeypatch.setitem(
        sys.modules,
        "requests",
        types.SimpleNamespace(RequestException=RequestException, HTTPError=HTTPError),
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_stage_b_test", stage_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    calls = []

    class Response:
        content = b"HEADER    ALPHAFOLD TEST STRUCTURE\nEND\n"

        def raise_for_status(self):
            return None

        def json(self):
            return []

    def fake_get(url, **_kwargs):
        calls.append(url)
        if "/api/prediction/" in url:
            error = module.requests.HTTPError("temporary AlphaFold API failure")
            raise error
        return Response()

    monkeypatch.setattr(module.requests, "get", fake_get, raising=False)
    monkeypatch.setattr(module, "RETRIEVAL_ATTEMPTS", 1)

    destination = tmp_path / "BACE1_P56817.pdb"
    module.fetch_alphafold_structure("P56817", destination)

    assert destination.read_bytes().startswith(b"HEADER")
    assert calls[0] == "https://alphafold.ebi.ac.uk/api/prediction/P56817"
    assert calls[1] == "https://alphafold.ebi.ac.uk/files/AF-P56817-F1-model_v6.pdb"


def test_continuous_service_live_mode_requires_native_adapter_contracts(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_live_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    try:
        module.run_service(
            {
                "mode": "live",
                "service": {"max_cycles": 1},
                "cluster_distribution": {"enabled": True},
            },
            tmp_path,
        )
    except RuntimeError as error:
        assert "candidate_generator" in str(error)
    else:  # pragma: no cover - protects the no-fallback contract
        raise AssertionError("live service accepted missing scientific adapters")


def test_continuous_service_requires_a_native_dispatcher_for_cross_box_runs(tmp_path):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    )
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_continuous_service_dispatch_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    configured_adapters = {
        name: {"command": [sys.executable, "-c", "print('{}')"]}
        for name in module.REQUIRED_ADAPTERS
    }
    config = {
        "mode": "live",
        **configured_adapters,
        "service": {"max_cycles": 1},
        "cluster_distribution": {"enabled": True},
    }
    try:
        module.run_service(config, tmp_path)
    except RuntimeError as error:
        assert "dispatch_command" in str(error)
    else:  # pragma: no cover - protects the cross-box fail-closed contract
        raise AssertionError("cross-box service accepted a missing native dispatcher")


def test_continuous_service_uses_embedded_config_when_bundle_config_is_not_mounted(
    tmp_path, monkeypatch
):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    )
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_runner_config_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "blueprint_root", lambda: tmp_path)
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({"mode": "mock", "service": {"max_cycles": 1}}),
    )

    assert module.load_config() == {"mode": "mock", "service": {"max_cycles": 1}}


def test_continuous_service_runner_starts_required_agent_beacon(tmp_path, monkeypatch):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    )
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_runner_beacon_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    started = []
    captured = {}
    monkeypatch.setattr(
        module, "start_agent_beacon_thread", lambda message: started.append(message)
    )
    monkeypatch.setattr(module, "run_dir", lambda: tmp_path)
    monkeypatch.setattr(
        module, "load_config", lambda: {"mode": "mock", "service": {"max_cycles": 1}}
    )
    monkeypatch.setattr(
        module, "service_main", lambda args: captured.setdefault("args", args)
    )

    module.main()

    assert started == ["Continuous drug discovery service is running"]
    assert captured["args"] == [
        "--config",
        str(tmp_path / "resolved_service_config.json"),
        "--run-dir",
        str(tmp_path),
    ]


def test_continuous_service_beacon_uses_runtime_stdout_contract(monkeypatch, capsys):
    service_path = (
        BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    )
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location(
        "drug_discovery_runner_beacon_payload_test", service_path
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setenv("MN_AGENT_BEACON_STDOUT_PREFIX", "__MN_AGENT_BEACON__")
    monkeypatch.setenv("MN_AGENT_BEACON_INTERVAL_MS", "not-a-number")
    module.start_agent_beacon_thread("service heartbeat")

    line = capsys.readouterr().out.strip()
    assert line.startswith("__MN_AGENT_BEACON__")
    payload = json.loads(line.removeprefix("__MN_AGENT_BEACON__"))
    assert payload["schema"] == "mn.agent.beacon.v1"
    assert payload["source"] == "agent"
    assert payload["status"] == "started"
    assert payload["message"] == "service heartbeat"
