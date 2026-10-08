from __future__ import annotations

from pathlib import Path

from mn_sdk import (
    build_deferred_runtime_model_plan,
    required_blueprint_models,
    run_input_validation,
    run_model_validation,
)
from mn_sdk.blueprints import blueprint_definition, read_blueprint, resolve_config
from mn_sdk.model_preparation import model_validation_inputs_with_prepared_models
from mn_sdk.submission_preparation import (
    manifest_nodes,
    prepare_manifest_for_submission,
)
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)


def test_cctv_operator_leaves_embedding_policy_to_the_rag_adapter():
    blueprint = ROOT / "cctv_operator"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data

    embedding_owned_keys = {
        "embedding_provider",
        "embedding_model",
        "embedding_api_base",
        "embedding_query_prefix",
        "embedding_document_prefix",
        "embedding_start_command",
        "embedding_healthcheck_enabled",
        "vector_dim",
    }
    rag_configs = (
        manifest["knowledge_rag"],
        config["knowledge_rag"],
    )

    for rag_config in rag_configs:
        assert embedding_owned_keys.isdisjoint(rag_config)
        assert rag_config["enabled"] is True
        assert rag_config["top_k"] == 4
        assert rag_config["chunk_size"] == 700
        assert rag_config["chunk_overlap"] == 70


def test_cctv_operator_uses_the_blueprint_owned_lazy_special_vlm_route():
    blueprint = ROOT / "cctv_operator"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data

    primary = manifest["runtime"]["models"]["primary"]
    vision = manifest["runtime"]["models"]["vision"]
    assert primary["model"] == "nemotron-3.5-lightning:latest"
    assert primary["type"] == "llm"
    assert vision["model"] == "cosmos3-nano-reasoner:1.7"
    assert vision["customize_mode"] is True
    assert vision["model_spec"]["source"] == "docker"
    assert vision["model_spec"]["docker"]["image"] == "nvcr.io/nim/nvidia/cosmos3-reasoner:1.7"
    assert config["llm"]["configs"]["primary"]["model"] == primary["model"]
    assert config["llm"]["configs"]["vision"]["model"] == vision["model"]
    visual_detector = next(node for node in manifest["agents"]["extra_nodes"] if node["node_id"] == "visual_detector")
    env = visual_detector["config"]["environment"]
    assert env["MN_VLM_MODEL"] == vision["model"]
    assert env["MN_VLM_BACKEND"] == "nim"
    assert env["MN_VLM_API_BASE"] == "auto"
    assert env["MN_RUNTIME_MODEL_MANAGED"] == "1"
    assert env["MN_VLM_MAX_TOKENS"] == "4096"
    deferred = build_deferred_runtime_model_plan(required_blueprint_models(manifest, config))
    assert deferred["errors"] == []
    assert {row["runtime_model"] for row in deferred["models"]} == {primary["model"], vision["model"]}
    validation_manifest, validation_config = (
        model_validation_inputs_with_prepared_models(
            manifest,
            config,
            model_install_summary=deferred,
        )
    )
    report = run_model_validation(
        blueprint,
        validation_manifest,
        config=validation_config,
    )

    assert report["ok"] is True
    assert report["issues"] == []


def test_cctv_operator_accepts_the_bundled_demo_before_submission(tmp_path):
    blueprint = ROOT / "cctv_operator"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data

    demo = tmp_path / "Camera.mp4"
    demo.write_bytes(b"fixture-video")
    config["video_source"]["demo_file"] = str(demo)

    report = run_input_validation(
        blueprint,
        manifest,
        config=config,
        env={
            "MN_ENV": "dev",
            "MN_HOME": str(tmp_path / ".mn"),
            "MN_SKILLS_ROOT": str(WORKSPACE / "mn-skills"),
            "MN_USE_LOCAL_SKILLS": "1",
            "PYTHONPATH": "",
        },
    )

    assert report["ok"] is True
    assert report["issues"] == []


def test_cctv_operator_rejects_an_empty_external_stream_before_submission(
    tmp_path,
):
    blueprint = ROOT / "cctv_operator"
    manifest = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    config = resolve_config(read_blueprint(blueprint)).data
    config["video_source"] = {
        **config["video_source"],
        "profile": "external",
        "uri": "",
    }

    report = run_input_validation(
        blueprint,
        manifest,
        config=config,
        env={
            "MN_ENV": "dev",
            "MN_HOME": str(tmp_path / ".mn"),
            "MN_SKILLS_ROOT": str(WORKSPACE / "mn-skills"),
            "MN_USE_LOCAL_SKILLS": "1",
            "PYTHONPATH": "",
        },
    )

    assert report["ok"] is False
    assert report["issues"][0]["code"] == "config.invalid_scheme"
    assert report["issues"][0]["location"]["path"] == "video_source.uri"


def test_cctv_execution_stays_in_dockerworkers_with_scoped_uploads(
    monkeypatch, tmp_path
):
    blueprint = ROOT / "cctv_operator"
    source = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    monkeypatch.setenv("MN_ENV", "dev")
    monkeypatch.setenv("MN_HOME", str(tmp_path / ".mn"))
    monkeypatch.setenv("MN_WORKSPACE_ROOT", str(WORKSPACE))
    monkeypatch.setenv("MN_SKILLS_ROOT", str(WORKSPACE / "mn-skills"))
    monkeypatch.setenv("MN_AGENTS_ROOT", str(WORKSPACE / "mn-agents"))

    prepared = prepare_manifest_for_submission(blueprint, source)
    nodes = {
        node["node_id"]: node
        for node in manifest_nodes(prepared)
        if node.get("node_id")
        in {
            "ingress",
            "adaptive_frame_sampler",
            "visual_detector",
            "report_writer",
            "cctv_web_ui",
        }
    }

    expected_uploads = {
        "ingress": {"agents/validation": "agents/validation"},
        "adaptive_frame_sampler": {
            "agents/adaptive_frame_sampler": "adaptive_frame_sampler",
            "domain": "adaptive_frame_sampler/domain",
        },
        "visual_detector": {
            "agents/visual_detector": "agents/visual_detector",
            "domain": "domain",
            "prompts": "prompts",
        },
        "report_writer": {
            "agents/report_writer": "agents/report_writer",
            "domain": "domain",
        },
        "cctv_web_ui": {"services": "services", "domain": "domain"},
    }
    expected_commands = {
        "ingress": ["python3", "agents/validation/start_video_monitor.py"],
        "adaptive_frame_sampler": [
            "bash",
            "scripts/run_sampler_on_nvidia.sh",
        ],
        "visual_detector": ["bash", "scripts/run_detector_on_nvidia.sh"],
        "report_writer": [
            "python3",
            "agents/report_writer/scripts/write_cctv_report.py",
        ],
        "cctv_web_ui": ["bash", "services/run_cctv_web_ui.sh"],
    }
    assert set(nodes) == set(expected_uploads)
    for node_id, node in nodes.items():
        config = node["config"]
        assert config["runner_module"] == "MirrorNeuron.Runner.DockerWorker"
        assert config["docker_worker_image"] == "docker_worker"
        assert config["image"] == "mirror-neuron/cctv-operator:local"
        assert config["network_mode"] == "host"
        assert "network" not in config
        assert config["gpus"] == "all"
        assert config["shared_container"] is True
        assert config["reuse_shared_container"] is True
        assert config["command"] == expected_commands[node_id]
        if node_id == "visual_detector":
            assert config["beacon_timeout_ms"] == 45_000
        assert "upload_path" not in config
        assert "upload_as" not in config
        upload_paths = {
            item["source"]: item["target"] for item in config["upload_paths"]
        }
        assert upload_paths == expected_uploads[node_id]
        assert "." not in upload_paths
        assert "docker_worker" not in upload_paths
        for source_path in upload_paths:
            assert (blueprint / "payloads" / source_path).exists()

    web_ui = nodes["cctv_web_ui"]
    assert "resources" not in web_ui
    assert "services" not in web_ui


def test_cctv_service_starts_its_single_monitor_run_immediately(monkeypatch, tmp_path):
    blueprint = ROOT / "cctv_operator"
    source = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    monkeypatch.setenv("MN_ENV", "dev")
    monkeypatch.setenv("MN_HOME", str(tmp_path / ".mn"))
    monkeypatch.setenv("MN_WORKSPACE_ROOT", str(WORKSPACE))
    monkeypatch.setenv("MN_SKILLS_ROOT", str(WORKSPACE / "mn-skills"))
    monkeypatch.setenv("MN_AGENTS_ROOT", str(WORKSPACE / "mn-agents"))

    prepared = prepare_manifest_for_submission(blueprint, source)

    assert source["type"] == "service"
    assert source["manifest"]["type"] == "service"
    assert source["service"] == {
        "enabled": True,
        "manual_close": "Stop the CCTV Operator job in OtterDesk or send SIGTERM.",
        "run_until": "manual_stop",
        "state_artifact": "monitoring_state.json",
    }
    assert prepared["type"] == "service"
    assert prepared["initial_inputs"]["ingress"] == [
        {
            "type": "cctv_operator_start",
            "payload": {"stream_id": "cctv_operator"},
        }
    ]


def test_cctv_visual_detector_preserves_the_payload_root(monkeypatch, tmp_path):
    blueprint = ROOT / "cctv_operator"
    source = blueprint_definition(read_blueprint(blueprint / "manifest.json"))
    monkeypatch.setenv("MN_ENV", "dev")
    monkeypatch.setenv("MN_HOME", str(tmp_path / ".mn"))
    monkeypatch.setenv("MN_WORKSPACE_ROOT", str(WORKSPACE))
    monkeypatch.setenv("MN_SKILLS_ROOT", str(WORKSPACE / "mn-skills"))
    monkeypatch.setenv("MN_AGENTS_ROOT", str(WORKSPACE / "mn-agents"))

    prepared = prepare_manifest_for_submission(blueprint, source)
    detector = next(
        node
        for node in manifest_nodes(prepared)
        if node.get("node_id") == "visual_detector"
    )
    config = detector["config"]
    upload_paths = {item["source"]: item["target"] for item in config["upload_paths"]}

    assert config["workdir"] == "/mn/job/agents/visual_detector"
    assert upload_paths == {
        "agents/visual_detector": "agents/visual_detector",
        "domain": "domain",
        "prompts": "prompts",
    }
    for source_path in upload_paths:
        assert (blueprint / "payloads" / source_path).exists()
