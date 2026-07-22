from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT_DIR = ROOT / "drug_discovery_research_assistant"
STEP_SCRIPTS = {
    "target_discovery": "scripts/stage_a.py",
    "structure_generation": "scripts/stage_b.py",
    "candidate_generation": "scripts/run_continuous_service.py",
    "binding_evaluation": "scripts/stage_d.py",
    "ranking_reporting": "scripts/stage_e.py",
}


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


def test_drug_discovery_manifest_uses_source_format_and_shared_blocks():
    manifest = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))

    assert manifest["apiVersion"] == "mn.workflow.source/v2"
    assert manifest["kind"] == "WorkflowSource"
    assert manifest["type"] == "service"
    assert manifest["identity"]["id"] == "drug_discovery_research_assistant"
    assert manifest["skill_dependencies"] == [
        {
            "type": "pip",
            "source": "gar",
            "name": "mirrorneuron-use-generic-model-skill",
            "version": "1.2.29",
        }
    ]
    assert {
        entry.get("from")
        for entry in manifest["config"]["manifest_defaults"]
        if isinstance(entry, dict)
    } >= {"contracts.inputs"}
    assert "nodes" not in manifest.get("agents", {})
    assert "edges" not in manifest.get("agents", {})
    assert [step["id"] for step in manifest["workflow"]["steps"]] == list(STEP_SCRIPTS)
    assert manifest["agents"].get("extra_templates", []) == []
    assert manifest["defaults"]["worker"]["uses"] == "mn-agents.worker.python_host@1"
    assert "python_environment" not in manifest["defaults"]["worker"]["with"]
    assert "blueprint_host_worker" in manifest["defaults"]["worker"]["with"]["stereotype"]
    assert {entry["source"] for entry in manifest["defaults"]["worker"]["with"]["upload_paths"]} == {
        "service",
        "domain",
        "biotarget",
    }
    for script in STEP_SCRIPTS.values():
        assert (BLUEPRINT_DIR / "payloads" / "service" / script).is_file(), script
    assert (BLUEPRINT_DIR / "payloads" / "prompts" / "scientific-review.md").is_file()
    assert manifest["service"]["run_until"] == "manual_stop"
    assert manifest["cluster_distribution"]["collaboration"]["mode"] == "cross_box_fanout_fanin"
    assert manifest["runtime"]["models"] == {
        "primary": {"provider": "docker_model_runner", "model": "default", "backend": "llama.cpp", "required": True}
    }
    assert manifest["requirements"]["gpu"] == {
        "driver": "cuda",
        "enforcement": "hard",
        "min_count": 1,
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
    assert gpu_worker["with"]["image"] == "mirror-neuron/drug-discovery-research-assistant:drugclip-gnina"

    assert {step["id"] for step in manifest["workflow"]["steps"]} == set(STEP_SCRIPTS)
    assert set(manifest["agents"]["registry"]) == set(STEP_SCRIPTS)
    for step in STEP_SCRIPTS:
        assert manifest["workflow"]["steps"][[item["id"] for item in manifest["workflow"]["steps"]].index(step)]["run"]["definition"] == f"steps.{step}"


def test_drug_discovery_model_profiles_match_vc_style_defaults():
    config = json.loads((BLUEPRINT_DIR / "config" / "default.json").read_text(encoding="utf-8"))

    assert config["mode"] == "live"
    assert config["execution"]["fake_science_adapters"] is False
    assert config["service"]["run_until"] == "manual_stop"
    assert config["service"]["max_cycles"] is None
    assert config["service"]["candidate_count"] == 160
    assert config["service"]["candidate_pool_size"] == 800
    assert config["service"]["drugclip_scoring_batch_size"] == 64
    assert config["resources"]["gpu"] == {
        "min_count": 1,
        "vendor": "nvidia",
        "driver": "cuda",
        "enforcement": "hard",
    }
    assert config["resources"]["required_capabilities"] == ["nvidia", "cuda"]
    assert config["outputs"]["folder_path"] == "~/Downloads/drug_discovery_research_assistant"
    assert config["llm"]["model"] == "default"
    assert "runtime_model" not in config["llm"]
    assert "preferred_model" not in config["llm"]
    assert "model" not in config["llm"]["configs"]["primary"]
    assert set(config["llm"]["configs"]) == {"primary"}
    assert "small_model_profile" not in config["llm"]
    assert "large_model_profile" not in config["llm"]
    assert {spec["llm_config"] for spec in config["llm"]["agents"].values()} == {"primary"}
    assert "runtime_model_key" not in config["drugclip"]
    assert config["drugclip"]["model_ref"] == "hf.co/homerquan/DrugClip"
    assert config["drugclip"]["generic_model"]["model_ref"] == "https://huggingface.co/homerquan/DrugClip"
    assert config["drugclip"]["generic_model"]["runtime"] == "native_checkpoint"
    assert config["drugclip"]["generic_model"]["validator"] == "mirrorneuron-use-generic-model-skill"
    assert config["drugclip"]["generic_model"]["shared_model_catalog"] is False
    assert config["drugclip"]["checkpoint_filename"] == "best.ckpt"
    assert config["drugclip"]["source_repository"] == "@/payloads"
    assert config["biotarget"]["source_dir"] == "@/payloads"
    assert config["python_dependencies"]["requirements"] == "requirements.txt"
    requirements = (BLUEPRINT_DIR / "payloads" / "requirements.txt").read_text(encoding="utf-8")
    for package in ("drugclip>=0.1.2", "torch>=2.0", "torch_geometric>=2.3", "requests"):
        assert package in requirements
    for adapter_name in ("candidate_generator", "folding", "drugclip", "simulation"):
        assert config[adapter_name]["command"][0] == "python3"
        assert config[adapter_name]["command"][1] == "scripts/biotarget_adapter.py"


def test_drug_discovery_source_manifest_expands_with_native_service_script():
    source = json.loads((BLUEPRINT_DIR / "manifest.json").read_text(encoding="utf-8"))
    expanded = _expand_source_manifest(source)

    assert expanded["type"] == "service"
    assert expanded["job_name"] == "drug-discovery-research-assistant"
    node_by_id = {node["node_id"]: node for node in expanded["agents"]["nodes"]}
    step_nodes = {
        node_id: node
        for node_id, node in node_by_id.items()
        if node_id.endswith(tuple(f"__{step}" for step in STEP_SCRIPTS))
    }
    assert {node_id.split("__", 1)[0] for node_id in step_nodes} == set(STEP_SCRIPTS)
    for step in STEP_SCRIPTS:
        config = step_nodes[f"{step}__{step}"]["config"]
        assert config["command"] == ["python3", "-m", "mn_sdk.step_runtime"]
        assert config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
        assert "python_environment" not in config
        assert config["gpus"] == "all"
        assert config["docker_worker_image"] == "docker_worker"
        assert config["image"] == "mirror-neuron/drug-discovery-research-assistant:drugclip-gnina"
    assert expanded["workflow"]["steps"]
    assert expanded["runtime"]["resources"]["gpu"] == {
        "driver": "cuda",
        "enforcement": "hard",
        "min_count": 1,
        "vendor": "nvidia",
    }


def test_drug_discovery_stage_environment_propagates_biotarget_source():
    operations = (BLUEPRINT_DIR / "payloads" / "domain" / "operations.py").read_text(encoding="utf-8")
    assert 'environment["BIOTARGET_SOURCE_DIR"] = str(bundled_source)' in operations


def test_drug_discovery_bundles_biotarget_and_prefers_it_at_runtime():
    assert (BLUEPRINT_DIR / "payloads" / "biotarget" / "pipeline.py").is_file()
    adapter = (BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "biotarget_adapter.py").read_text(encoding="utf-8")
    assert 'bundled / "biotarget" / "pipeline.py"' in adapter
    assert "configured = os.environ" not in adapter
    assert "normalize_model_reference" in adapter
    assert "prepare_model(" not in adapter
    assert "drugclip_scoring_batch_size" in adapter
    assert "requires an NVIDIA CUDA PyTorch runtime" in adapter
    service = (BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py").read_text(encoding="utf-8")
    assert '"candidates": candidates' in service
    assert "DrugClip batch adapter returned incomplete target-candidate scores." in service
    operations = (BLUEPRINT_DIR / "payloads" / "domain" / "operations.py").read_text(encoding="utf-8")
    assert 'capture_output = script != "run_continuous_service.py"' in operations
    continuous_service = (BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py").read_text(encoding="utf-8")
    assert "stdout (tail)" in continuous_service
    stage_a = (BLUEPRINT_DIR / "payloads" / "biotarget" / "stages" / "stage_a_discovery.py").read_text(encoding="utf-8")
    stage_d = (BLUEPRINT_DIR / "payloads" / "biotarget" / "stages" / "stage_d_evaluation.py").read_text(encoding="utf-8")
    assert "_mock_targets" not in stage_a
    assert "surrogate docking" not in stage_d
    assert 'shutil.which("gnina")' in stage_d
    assert '"docker",' not in stage_d
    assert "requires_gnina_cpu_emulation" not in stage_d
    dockerfile = (BLUEPRINT_DIR / "payloads" / "docker_worker" / "Dockerfile").read_text(encoding="utf-8")
    assert "nvidia/cuda:13.0.0-cudnn-devel-ubuntu24.04" in dockerfile
    assert "GNINA_VERSION=v1.3.2" in dockerfile
    assert "CMAKE_CUDA_ARCHITECTURES=121" in dockerfile
    assert "python3 -m venv /opt/mn-venv" in dockerfile
    assert "/opt/mn-venv/lib/python3.12/site-packages/torch/lib" in dockerfile


def test_continuous_service_fake_mode_writes_parallel_cycle_artifacts(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    config = {
        "mode": "mock",
        "execution": {"fake_science_adapters": True},
        "service": {"max_cycles": 1, "cycle_interval_seconds": 0.1, "simulation_top_k": 2, "parallelism": {"folding_workers": 2, "drugclip_workers": 2, "simulation_workers": 2}},
        "cluster_distribution": {"enabled": False, "worker_pools": {}},
        "inputs": {"payload": {"targets": [{"protein_id": "P56817", "gene": "BACE1"}]}},
    }
    result = module.run_service(config, tmp_path)

    assert result["status"] == "stopped"
    assert result["completed_cycles"] == 1
    cycle = tmp_path / "cycles" / "cycle-000000"
    for name in ("generated_candidates.json", "folding_results.json", "drugclip_screening.json", "simulation_results.json", "cycle_report.json"):
        assert (cycle / name).exists(), name
    report = json.loads((cycle / "cycle_report.json").read_text(encoding="utf-8"))
    assert report["mode"] == "fake_smoke_test"
    assert report["simulation_count"] > 0


def test_continuous_service_publishes_user_facing_candidates(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_output_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    output_folder = tmp_path / "Downloads" / "drug_discovery_research_assistant"
    config = {
        "mode": "mock",
        "execution": {"fake_science_adapters": True},
        "service": {"max_cycles": 1, "simulation_top_k": 1, "parallelism": {"folding_workers": 1, "drugclip_workers": 1, "simulation_workers": 1}},
        "cluster_distribution": {"enabled": False},
        "inputs": {"payload": {"output_folder": str(output_folder), "targets": [{"protein_id": "P56817", "gene": "BACE1"}]}},
    }

    module.run_service(config, tmp_path / "run")

    candidates = json.loads((output_folder / "candidates.json").read_text(encoding="utf-8"))
    assert candidates["schema_version"] == "mn.blueprint.staged_candidates.v1"
    assert candidates["candidate_count"] == len(candidates["candidates"]) > 0
    assert (output_folder / "latest_cycle_report.json").exists()
    status = json.loads((output_folder / "service_status.json").read_text(encoding="utf-8"))
    assert status["status"] == "stopped"
    assert status["completed_cycles"] == 1


def test_continuous_service_repeats_generation_and_simulation_until_stop_file(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_loop_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    calls = []

    def fake_cycle(config, run_dir, cycle_id):
        calls.append(cycle_id)
        report = {"cycle_id": cycle_id, "top_candidates": [{"candidate": {"smiles": "C"}}]}
        if len(calls) == 2:
            (run_dir / "STOP").touch()
        return report

    module.run_cycle = fake_cycle
    result = module.run_service(
        {
            "mode": "mock",
            "service": {"max_cycles": None, "cycle_interval_seconds": 0.1, "stop_file": "${MN_RUN_DIR}/STOP"},
            "cluster_distribution": {"enabled": False},
        },
        tmp_path,
    )

    assert calls == [0, 1]
    assert result["completed_cycles"] == 2
    assert result["stop_reason"] == "stop_file"


def test_continuous_service_uses_unique_work_directories_for_parallel_jobs(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_paths_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    first = module.job_artifact_dir(tmp_path, "drugclip", "P12345", "candidate-1")
    second = module.job_artifact_dir(tmp_path, "drugclip", "P67890", "candidate-1")
    assert first != second
    assert first.parent == second.parent == tmp_path / "drugclip"


def test_biotarget_adapter_makes_folded_structure_path_absolute(tmp_path):
    adapter_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "biotarget_adapter.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_biotarget_adapter_path_test", adapter_path)
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


def test_continuous_service_live_mode_requires_native_adapter_contracts(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_live_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    try:
        module.run_service({"mode": "live", "service": {"max_cycles": 1}, "cluster_distribution": {"enabled": True}}, tmp_path)
    except RuntimeError as error:
        assert "candidate_generator" in str(error)
    else:  # pragma: no cover - protects the no-fallback contract
        raise AssertionError("live service accepted missing scientific adapters")


def test_continuous_service_requires_a_native_dispatcher_for_cross_box_runs(tmp_path):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "continuous_service.py"
    spec = importlib.util.spec_from_file_location("drug_discovery_continuous_service_dispatch_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    configured_adapters = {name: {"command": [sys.executable, "-c", "print('{}')"]} for name in module.REQUIRED_ADAPTERS}
    config = {"mode": "live", **configured_adapters, "service": {"max_cycles": 1}, "cluster_distribution": {"enabled": True}}
    try:
        module.run_service(config, tmp_path)
    except RuntimeError as error:
        assert "dispatch_command" in str(error)
    else:  # pragma: no cover - protects the cross-box fail-closed contract
        raise AssertionError("cross-box service accepted a missing native dispatcher")


def test_continuous_service_uses_embedded_config_when_bundle_config_is_not_mounted(tmp_path, monkeypatch):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location("drug_discovery_runner_config_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    monkeypatch.setattr(module, "blueprint_root", lambda: tmp_path)
    monkeypatch.setenv("MN_BLUEPRINT_CONFIG_JSON", json.dumps({"mode": "mock", "service": {"max_cycles": 1}}))

    assert module.load_config() == {"mode": "mock", "service": {"max_cycles": 1}}


def test_continuous_service_runner_starts_required_agent_beacon(tmp_path, monkeypatch):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location("drug_discovery_runner_beacon_test", service_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    started = []
    captured = {}
    monkeypatch.setattr(module, "start_agent_beacon_thread", lambda message: started.append(message))
    monkeypatch.setattr(module, "run_dir", lambda: tmp_path)
    monkeypatch.setattr(module, "load_config", lambda: {"mode": "mock", "service": {"max_cycles": 1}})
    monkeypatch.setattr(module, "service_main", lambda args: captured.setdefault("args", args))

    module.main()

    assert started == ["Continuous drug discovery service is running"]
    assert captured["args"] == ["--config", str(tmp_path / "resolved_service_config.json"), "--run-dir", str(tmp_path)]


def test_continuous_service_beacon_uses_runtime_stdout_contract(monkeypatch, capsys):
    service_path = BLUEPRINT_DIR / "payloads" / "service" / "scripts" / "run_continuous_service.py"
    monkeypatch.syspath_prepend(str(service_path.parent))
    spec = importlib.util.spec_from_file_location("drug_discovery_runner_beacon_payload_test", service_path)
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
