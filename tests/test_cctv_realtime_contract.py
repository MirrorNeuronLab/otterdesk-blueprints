"""The replacement is a real native Compose + monitored-service blueprint."""

import json
from pathlib import Path

import yaml
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"


def test_replacement_compiles_with_native_ownership_and_secure_setup():
    package = read_blueprint(ROOT)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package).manifest
    nodes = {node["node_id"]: node for node in compiled["agents"]["nodes"]}
    assert set(nodes) == {"realtime_vlm", "camera_operator"}
    assert nodes["realtime_vlm"]["config"]["runner_module"] == "MirrorNeuron.Runner.DockerCompose"
    assert nodes["camera_operator"]["config"]["environment"]["MN_WORKFLOW_STEP_HANDLER"] == "mn_sdk.integrations.block_auxiliary"
    operator = nodes["camera_operator"]
    assert operator["config"]["runner_module"] == "MirrorNeuron.Runner.HostLocal"
    assert "network_mode" not in operator["config"]
    assert operator["config"]["python_environment"]["python_version"] == "3.12"
    assert {port["label"] for port in operator["resources"]["ports"]} == {"web_ui", "cctv_operator_mcp"}
    assert source["requirements"]["gpu"]["enforcement"] == "hard"
    assert source["requirements"]["gpu"]["min_memory_mb"] == 49152
    assert compiled["metadata"]["mn_blocks_lock"]["services"]["camera_operator"]["uses"] == "mn.blocks.monitored_service@1"
    config = resolve_config(package).data
    assert config["video_source"]["uri"] == ""
    assert config["vlm"]["base_url"] == "http://otterdesk-cctv-vlm:8000"
    for guide in [source["metadata"]["setup_guide"], source["metadata"]["init_config_review"]]:
        field = next(field for field in guide["fields"] if field["path"] == "video_source.uri")
        assert field["required"] is field["secret"] is True
        assert set(field["protocols"]) == {"rtsp:", "rtsps:"}
    assert not source["metadata"]["setup_guide"]["sample"]["available"]
    assert not source["runtime"].get("models")
    assert "mn.agentic" not in package.manifest["extensions"]
    assert source["knowledge_rag"]["enabled"] is True
    assert source["knowledge_rag"]["top_k"] == 4


def test_vss_recipe_matches_the_sample_and_has_persistent_local_model_caches():
    compose = yaml.safe_load((ROOT / "payloads/vss/compose.yaml").read_text())
    vlm = compose["services"]["vlm"]
    assert vlm["image"].endswith("sha256:f539300f249e3d30528a986deac6796a8c89e8e9c431bb4357d504fbd173541c}")
    assert vlm["gpus"] == "all"
    assert vlm["ports"] == ["127.0.0.1:8019:8000"]
    env = vlm["environment"]
    assert env["VLLM_USE_AOT_COMPILE"] == "0"
    assert env["VLLM_DISABLE_COMPILE_CACHE"] == "1"
    assert env["VLLM_MAX_NUM_SEQS"] == "1"
    assert env["ENABLE_OTEL_MONITORING"] == "false"
    assert env["KAFKA_ENABLED"] == "false"
    assert not {"HF_TOKEN", "NGC_API_KEY", "RTSP_URL"} & env.keys()
    assert compose["volumes"]["hf-cache"]["name"] == "otterdesk-cctv-hf-cache"
    assert all(volume["external"] for volume in compose["volumes"].values())
    assert compose["networks"]["runtime"]["external"] is True
    assert vlm["networks"]["runtime"]["aliases"] == ["otterdesk-cctv-vlm"]


def test_retired_pipeline_and_inapplicable_tools_are_removed():
    for filename in ["person_detector.py", "live_monitor.py", "vision_model.py", "mobileclip.py", "sampling.py"]:
        assert not (ROOT / "payloads/domain" / filename).exists()
    tools = json.loads((ROOT / "extensions/mcp.json").read_text())["tools"]
    assert set(tools) == {"get_operator_status", "get_operator_activity", "set_monitoring_instruction", "get_video_history", "get_pipeline_benchmarks"}
    assert not (ROOT / "payloads/services/cctv_operator_mcp.py").exists()
    preflight = json.loads((ROOT / "extensions/mcp.json").read_text())["preflight"]
    assert preflight["required_for_effects"] == ["monitoring"]
    assert set(preflight["required_for_effects"]) <= {tool["effect"] for tool in tools.values()}
