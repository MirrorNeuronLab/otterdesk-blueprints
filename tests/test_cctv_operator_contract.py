from __future__ import annotations

import json
from pathlib import Path

from mn_sdk import run_input_validation
from otterdesk_blueprint_suite import (
    test_cctv_operator_declares_domain_agent_aliases,
    test_cctv_operator_declares_otterdesk_chat_system_prompt,
    test_cctv_operator_detector_script_compiles_with_shared_helper_import,
    test_cctv_operator_default_contract_is_stream_only,
    test_cctv_operator_rejects_folder_mode,
    test_cctv_operator_seeds_live_monitor_start_message,
    test_cctv_operator_stream_validator_probes_rtsp_and_rtmp,
    test_cctv_operator_stream_validator_rejects_non_stream_uri,
    test_cctv_operator_uses_dockerworker_nvidia_media_worker,
    test_cctv_operator_owns_json_render_web_ui_and_uses_generic_skills,
)


ROOT = Path(__file__).resolve().parents[1]


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
            "MN_SKILLS_ROOT": str(ROOT.parent / "mn-skills"),
            "MN_USE_LOCAL_SKILLS": "1",
            "PYTHONPATH": "",
        },
    )

    assert report["ok"] is False
    assert report["issues"][0]["code"] == "config.invalid_scheme"
    assert report["issues"][0]["location"]["path"] == "video_source.uri"
