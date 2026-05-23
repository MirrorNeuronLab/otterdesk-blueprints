from __future__ import annotations

import importlib.util
import json
import py_compile
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT.parent
SUPPORT_SRC = WORKSPACE / "mn-skills" / "blueprint_support_skill" / "src"
AGENTS_ROOT = WORKSPACE / "mn-agents"
if str(SUPPORT_SRC) not in sys.path:
    sys.path.insert(0, str(SUPPORT_SRC))

from mn_blueprint_support import render_manifest_agent_templates
from mn_blueprint_support.openshell_network import (
    build_openshell_network_policy,
    endpoint_from_uri,
    write_openshell_network_policy,
)


def _manifest_paths() -> list[Path]:
    return sorted(path / "manifest.json" for path in ROOT.iterdir() if (path / "manifest.json").exists())


def test_otterdesk_blueprints_declare_membrane_context_memory_layer():
    for manifest_path in _manifest_paths():
        blueprint_dir = manifest_path.parent
        manifest = json.loads(manifest_path.read_text())
        config = json.loads((blueprint_dir / "config" / "default.json").read_text())
        blueprint_id = manifest["metadata"]["blueprint_id"]
        expected_namespace = f"{blueprint_id}_context"

        config_layer = config.get("memory_layer")
        manifest_layer = manifest["metadata"].get("memory_layer")
        assert config_layer == manifest_layer, blueprint_dir.name
        assert config_layer["enabled"] is True
        assert config_layer["enabled_env"] == "MN_CONTEXT_MEMORY_ENABLED"
        assert config_layer["conversation_enabled"] is True
        assert config_layer["conversation_enabled_env"] == "OTTERDESK_CONTEXT_MEMORY_ENABLED"
        assert config_layer["namespace"] == expected_namespace
        assert config_layer["collection"] == "mn_memory"
        assert config_layer["sdk_distribution"] == "mirrorneuron-membrane-python-sdk"
        assert config_layer["sdk_import_package"] == "mn_context_engine_sdk"
        assert config_layer["project_path"] == "${MN_MEMBRANE_PROJECT_PATH}"
        assert config_layer["python_sdk_path"] == "${MN_MEMBRANE_SDK_PATH}"

        conversation = config_layer["conversation"]
        assert conversation["agent_role"] == "otterdesk_chat"
        assert conversation["include_runtime_events"] is True
        assert conversation["include_runtime_logs"] is True
        assert conversation["include_human_events"] is True
        assert conversation["token_budget"] > conversation["target_tokens"] > 0
        assert "Membrane context memory optimization" in manifest["metadata"]["runtime_features"]


def test_index_entries_point_to_loadable_blueprint_folders():
    index = json.loads((ROOT / "index.json").read_text())
    assert index
    ids = [entry["id"] for entry in index]
    assert len(ids) == len(set(ids))

    for entry in index:
        blueprint_dir = ROOT / entry["path"]
        manifest_path = blueprint_dir / "manifest.json"
        assert blueprint_dir.exists(), entry
        assert manifest_path.exists(), entry
        manifest = json.loads(manifest_path.read_text())
        assert manifest["metadata"]["blueprint_id"] == entry["id"]
        assert manifest["graph_id"] == entry["graph_id"]
        assert manifest["job_name"] == entry["job_name"]


def test_otterdesk_nodes_use_shared_agent_templates_and_render():
    for manifest_path in _manifest_paths():
        manifest = json.loads(manifest_path.read_text())
        assert manifest.get("nodes"), manifest_path
        for node in manifest["nodes"]:
            assert "uses" in node, (manifest_path.parent.name, node.get("node_id"))
            assert node["uses"].startswith("mn-agents."), (manifest_path.parent.name, node.get("node_id"))
            assert "@" in node["uses"] and not node["uses"].endswith("@latest")
            assert isinstance(node.get("with"), dict), (manifest_path.parent.name, node.get("node_id"))
            assert not {"agent_type", "type", "role", "config"} & set(node), (
                manifest_path.parent.name,
                node.get("node_id"),
            )

        rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
        assert len(rendered["nodes"]) == len(manifest["nodes"])
        assert all("uses" not in node and "with" not in node for node in rendered["nodes"])


def test_video_watch_openshell_policy_is_generated_by_shared_helper(tmp_path):
    blueprint_dir = ROOT / "video_watch_assistant"
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    network = config["openshell_network"]
    assert manifest["metadata"]["openshell_network"] == network

    endpoints = [
        endpoint_from_uri(
            item["name"],
            item["uri"],
            item["binaries"],
            allowed_ips=item.get("allowed_ips"),
            allow_any_ip=bool(item.get("allow_any_ip")),
        )
        for item in network["endpoints"]
    ]
    generated_policy = build_openshell_network_policy(endpoints, include_dns=network.get("include_dns", True))
    generated_path = write_openshell_network_policy(generated_policy, tmp_path / "video-egress.yaml")
    committed_path = blueprint_dir / "payloads" / network["policy_path"]

    assert generated_path.read_text() == committed_path.read_text()
    assert "0.0.0.0/0" not in committed_path.read_text()

    rendered = render_manifest_agent_templates(manifest, AGENTS_ROOT)
    visual_node = next(node for node in rendered["nodes"] if node["node_id"] == "visual_detector")
    assert visual_node["config"]["policy"] == network["policy_path"]
    assert visual_node["config"]["upload_paths"] == [{"source": "visual_detector", "target": "visual_detector"}]
    assert "PYTHONPATH" not in visual_node["config"]["environment"]


def test_video_watch_detector_script_compiles_with_shared_helper_import():
    py_compile.compile(
        str(ROOT / "video_watch_assistant" / "payloads" / "visual_detector" / "scripts" / "analyze_video_frame.py"),
        doraise=True,
    )


def test_video_watch_pre_launch_owns_mediamtx_preview_config():
    blueprint_dir = ROOT / "video_watch_assistant"
    config = json.loads((blueprint_dir / "config" / "default.json").read_text())
    manifest = json.loads((blueprint_dir / "manifest.json").read_text())
    script = (blueprint_dir / "scripts" / "pre-launch.sh").read_text()
    cleanup_script = (blueprint_dir / "scripts" / "post-launch.sh").read_text()

    assert "webrtc: true" in script
    assert "choose_available_webrtc_ports" in script
    assert "BROWSER_PREVIEW_URI" in script
    assert "MN_POST_LAUNCH_STATE_FILE" in script
    assert "post_launch_state.json" in script
    assert "pre_launch_preflight" in script
    assert '"browser_video_source": "${BROWSER_PREVIEW_URI}"' in script
    assert '"browser_publish_source": "disabled"' in script
    assert '"cleanup_script": "scripts/post-launch.sh"' in script
    assert "terminate_mediamtx_on_port" in cleanup_script
    assert "RTSP_PORT" in cleanup_script
    assert "WEBRTC_PORT" in cleanup_script

    dashboard = config["web_ui"]["dashboard"]
    assert dashboard["browser_video_source"] == "disabled"
    assert dashboard["browser_publish_source"] == "disabled"
    assert dashboard["video_preview_bridge"]["enabled"] is False
    assert dashboard["video_preview_bridge"]["auto_start"] is False
    assert dashboard["video_preview_bridge"]["cleanup_script"] == "scripts/post-launch.sh"

    manifest_web_ui = manifest["metadata"]["web_ui"]
    assert manifest_web_ui["browser_video_source"] == "disabled"
    assert manifest_web_ui["browser_publish_source"] == "disabled"
    assert manifest_web_ui["video_preview_bridge"]["enabled"] is False
    assert manifest_web_ui["video_preview_bridge"]["auto_start"] is False
    assert manifest_web_ui["video_preview_bridge"]["cleanup_script"] == "scripts/post-launch.sh"


def _load_video_watch_validator():
    path = ROOT / "video_watch_assistant" / "payloads" / "validation" / "validate_rtsp_source.py"
    spec = importlib.util.spec_from_file_location("video_watch_validate_rtsp_source", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_video_watch_default_validator_checks_demo_video(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    demo = tmp_path / "sample.mp4"
    demo.write_bytes(b"fake-video")
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8554/video-watch",
                "demo_video": str(demo),
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="video\n", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator.main() == 0
    assert str(demo) in calls[0]
    assert "-rtsp_transport" not in calls[0]


def test_video_watch_dynamic_mapped_validator_skips_ffprobe_when_missing(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    demo = tmp_path / "sample.mp4"
    demo.write_bytes(b"fake-video")
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8567/video-watch",
                "demo_video": str(demo),
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: None)

    def fail_run(*_args, **_kwargs):
        raise AssertionError("demo mapped endpoint should not require ffprobe")

    monkeypatch.setattr(validator.subprocess, "run", fail_run)

    assert validator.main() == 0


def test_video_watch_runtime_bundle_allows_host_validated_demo_video(monkeypatch, tmp_path):
    validator = _load_video_watch_validator()
    runtime_bundle = tmp_path / "bundle_123"
    runtime_bundle.mkdir()
    monkeypatch.chdir(runtime_bundle)
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({
            "video_source": {
                "uri": "rtsp://127.0.0.1:8567/video-watch",
                "demo_video": "data/sample.mp4",
            }
        }),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: None)
    monkeypatch.setattr(validator.Path, "cwd", lambda: Path("/tmp/bundle_123"))

    assert validator.main() == 0


def test_video_watch_external_rtsp_validator_probes_stream(monkeypatch):
    validator = _load_video_watch_validator()
    monkeypatch.setenv(
        "MN_BLUEPRINT_CONFIG_JSON",
        json.dumps({"video_source": {"uri": "rtsp://camera.example/live"}}),
    )
    monkeypatch.setattr(validator.shutil, "which", lambda _name: "/usr/bin/ffprobe")
    calls = []

    def fake_run(command, **_kwargs):
        calls.append(command)
        return subprocess.CompletedProcess(command, 0, stdout="video\n", stderr="")

    monkeypatch.setattr(validator.subprocess, "run", fake_run)

    assert validator.main() == 0
    assert "rtsp://camera.example/live" in calls[0]
    assert "-rtsp_transport" in calls[0]
