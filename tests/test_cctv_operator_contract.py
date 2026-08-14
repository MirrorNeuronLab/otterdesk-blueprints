from __future__ import annotations

import json
from pathlib import Path

from mn_sdk import run_input_validation
from mn_sdk.submission_preparation import (
    manifest_nodes,
    prepare_manifest_for_submission,
)
from otterdesk_blueprint_suite import (
    test_cctv_operator_declares_domain_agent_aliases,
    test_cctv_operator_declares_otterdesk_chat_system_prompt,
    test_cctv_operator_detector_script_compiles_with_shared_helper_import,
    test_cctv_operator_default_contract_is_stream_only,
    test_cctv_operator_rejects_folder_mode,
    test_cctv_operator_seeds_live_monitor_start_message,
    test_cctv_operator_stream_validator_defers_probe_without_local_ffprobe,
    test_cctv_operator_stream_validator_probes_rtsp_and_rtmp,
    test_cctv_operator_stream_validator_rejects_non_stream_uri,
    test_cctv_operator_uses_dockerworker_nvidia_media_worker,
    test_cctv_operator_owns_json_render_web_ui_and_uses_generic_skills,
)
from workspace_paths import companion_workspace


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = companion_workspace(ROOT)


def test_cctv_operator_rejects_empty_stream_before_submission(tmp_path):
    blueprint = ROOT / "cctv_operator"
    manifest = json.loads((blueprint / "manifest.json").read_text())
    config = json.loads((blueprint / "config" / "default.json").read_text())

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


def test_cctv_hostlocal_commands_use_the_normalized_payload_root(
    monkeypatch, tmp_path
):
    blueprint = ROOT / "cctv_operator"
    source = json.loads((blueprint / "manifest.json").read_text())
    monkeypatch.setenv("MN_ENV", "dev")
    monkeypatch.setenv("MN_HOME", str(tmp_path / ".mn"))
    monkeypatch.setenv("MN_WORKSPACE_ROOT", str(WORKSPACE))
    monkeypatch.setenv("MN_SKILLS_ROOT", str(WORKSPACE / "mn-skills"))
    monkeypatch.setenv("MN_AGENTS_ROOT", str(WORKSPACE / "mn-agents"))

    prepared = prepare_manifest_for_submission(blueprint, source)
    nodes = {
        node["node_id"]: node
        for node in manifest_nodes(prepared)
        if node.get("node_id") in {"report_writer", "cctv_web_ui"}
    }

    assert set(nodes) == {"report_writer", "cctv_web_ui"}
    for node in nodes.values():
        config = node["config"]
        assert config["upload_path"] == "."
        assert config["upload_as"] == "."
        assert config["workdir"] == "/sandbox/job"
        assert "upload_paths" not in config
        assert (blueprint / "payloads" / config["command"][1]).is_file()


def test_cctv_visual_detector_preserves_the_payload_root(monkeypatch, tmp_path):
    blueprint = ROOT / "cctv_operator"
    source = json.loads((blueprint / "manifest.json").read_text())
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
    upload_paths = {
        item["source"]: item["target"] for item in config["upload_paths"]
    }

    assert config["workdir"] == "/mn/job/agents/visual_detector"
    assert upload_paths == {
        "agents/visual_detector": "agents/visual_detector",
        "domain": "domain",
        "prompts": "prompts",
    }
    for source_path in upload_paths:
        assert (blueprint / "payloads" / source_path).exists()
