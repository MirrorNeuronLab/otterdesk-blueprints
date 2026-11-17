"""The replacement is a real native Compose + monitored-service blueprint."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
import yaml
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config

from cctv_operator.payloads.domain.settings import camera_settings

ROOT = Path(__file__).resolve().parents[1] / "cctv_operator"
SAMPLE_ROOT = "rtsp://127.0.0.1:8554/stream"


def four_cameras():
    return {"video_source": {"count": 4, "uri": f"{SAMPLE_ROOT}/1", **{
        f"camera_{slot}": {"uri": f"{SAMPLE_ROOT}/{slot}"} for slot in range(2, 5)
    }}}


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
    assert {port["label"] for port in operator["resources"]["ports"]} == {"web_ui", "cctv_operator_mcp"}
    assert source["requirements"]["gpu"]["enforcement"] == "hard"
    assert source["requirements"]["gpu"]["min_memory_mb"] == 49152
    assert compiled["metadata"]["mn_blocks_lock"]["services"]["camera_operator"]["uses"] == "mn.blocks.monitored_service@1"
    config = resolve_config(package).data
    assert config["video_source"]["uri"] == ""
    assert config["video_source"]["count"] == 1
    assert config["vlm"]["base_url"] == "http://otterdesk-cctv-vlm:8000"
    assert config["source_context"]["enabled"] is True
    assert any(package.startswith("sentence-transformers") for package in operator["config"]["python_environment"]["packages"])
    for guide in [source["metadata"]["setup_guide"], source["metadata"]["init_config_review"]]:
        fields = {field["path"]: field for field in guide["fields"]}
        assert fields["inputs.payload.monitoring_goal"]["type"] == "textarea"
        assert [choice["value"] for choice in fields["video_source.count"]["choices"]] == [1, 2, 3, 4]
        for slot in range(1, 5):
            path = "video_source.uri" if slot == 1 else f"video_source.camera_{slot}.uri"
            field = fields[path]
            assert field["required"] is field["secret"] is True
            assert set(field["protocols"]) == {"rtsp:", "rtsps:"}
            if slot > 1:
                assert [condition["equals"] for condition in field["active_when_any"]] == list(range(slot, 5))
    assert not source["metadata"]["setup_guide"]["sample"]["available"]
    assert not source["runtime"].get("models")
    assert "mn.agentic" not in package.manifest["extensions"]
    assert source["knowledge_rag"]["enabled"] is True
    assert source["knowledge_rag"]["top_k"] == 4


@pytest.mark.parametrize("count", [1, 2, 3, 4])
def test_setup_accepts_one_to_four_active_streams(count):
    config = four_cameras()
    config["video_source"]["count"] = count
    cameras = camera_settings(config)
    assert [camera.uri for camera in cameras] == [f"{SAMPLE_ROOT}/{slot}" for slot in range(1, count + 1)]
    assert len({camera.source_id for camera in cameras}) == count
    assert camera_settings({"video_source": {"uri": cameras[0].uri}})[0].source_id == cameras[0].source_id


def test_configured_goals_validate_before_a_run(monkeypatch):
    from cctv_operator.payloads.agents.validation.validate_video_source import main

    config = four_cameras()
    config["inputs"] = {"payload": {"monitoring_goal": "No safety helmet\r\n\nOpen door"}}
    assert {camera.prompt for camera in camera_settings(config)} == {"No safety helmet\nOpen door"}
    config["inputs"]["payload"]["monitoring_goal"] = "\n".join(f"Condition {i}" for i in range(6))
    monkeypatch.setenv("MN_BLUEPRINT_CONFIG_JSON", json.dumps(config))
    with pytest.raises(ValueError, match="up to five"):
        camera_settings(config)
    assert main() == 1


@pytest.mark.parametrize("overrides,message", [
    ({"count": 0}, "1 and 4"),
    ({"count": 5}, "1 and 4"),
    ({"count": True}, "1 and 4"),
    ({"camera_4": {}}, "camera 4"),
    ({"camera_3": {"uri": "https://secret@example.com/live"}}, "camera 3"),
    ({"camera_2": {"uri": "rtsp://private:secret@127.0.0.1:8554/stream/1"}}, "different stream"),
])
def test_setup_and_operator_reject_the_same_invalid_stream_config_without_echoing_input(overrides, message):
    config = four_cameras()
    config["video_source"].update(overrides)
    with pytest.raises(ValueError, match=message):
        camera_settings(config)
    result = subprocess.run([sys.executable, "payloads/agents/validation/validate_video_source.py"], cwd=ROOT,
                            env={**os.environ, "MN_BLUEPRINT_CONFIG_JSON": json.dumps(config)}, capture_output=True, text=True)
    assert result.returncode == 1, result.stderr
    assert message in json.loads(result.stdout)["issues"][0]["message"]
    assert "secret" not in result.stdout + result.stderr


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
    assert set(tools) == {"get_operator_status", "get_operator_activity", "set_monitoring_goals", "get_video_history", "answer_video_question", "get_pipeline_benchmarks"}
    assert tools["set_monitoring_goals"]["inputSchema"]["properties"]["goals"]["maxItems"] == 5
    assert not (ROOT / "payloads/services/cctv_operator_mcp.py").exists()
    preflight = json.loads((ROOT / "extensions/mcp.json").read_text())["preflight"]
    assert preflight["required_for_effects"] == ["monitoring"]
    assert set(preflight["required_for_effects"]) <= {tool["effect"] for tool in tools.values()}
