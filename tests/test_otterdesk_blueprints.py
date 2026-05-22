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
    assert {"source": "../mirror-neuron-set/mn-skills/blueprint_support_skill", "target": "mn-skills/blueprint_support_skill"} in visual_node["config"]["upload_paths"]
    assert visual_node["config"]["environment"]["PYTHONPATH"] == "../mn-skills/blueprint_support_skill/src"


def test_video_watch_detector_script_compiles_with_shared_helper_import():
    py_compile.compile(
        str(ROOT / "video_watch_assistant" / "payloads" / "visual_detector" / "scripts" / "analyze_video_frame.py"),
        doraise=True,
    )


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
