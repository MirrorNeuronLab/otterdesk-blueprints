from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DETECTOR_PATH = ROOT / "cctv_operator" / "payloads" / "visual_detector" / "scripts" / "analyze_video_frame.py"


def _load_detector():
    spec = importlib.util.spec_from_file_location("cctv_operator_detector_helpers", DETECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_parse_model_json_accepts_fenced_embedded_and_repaired_objects():
    detector = _load_detector()

    parsed, error = detector.parse_model_json('```json\n{"detected": true, "confidence": 0.8}\n```')
    assert error == ""
    assert parsed == {"detected": True, "confidence": 0.8}

    parsed, error = detector.parse_model_json('model said: {"detected": false, "risk_level": "low"} done')
    assert error == ""
    assert parsed["risk_level"] == "low"

    parsed, error = detector.parse_model_json('{"detected": true\n"confidence": 0.5,}')
    assert error == ""
    assert parsed == {"detected": True, "confidence": 0.5}


def test_source_uri_helpers_preserve_ports_and_detect_safe_retries():
    detector = _load_detector()

    assert detector.source_uri_with_host("rtsp://user:pass@127.0.0.1:8554/cctv", "host.docker.internal") == (
        "rtsp://user:pass@host.docker.internal:8554/cctv"
    )
    assert detector.stream_fallback_sources("rtsp://camera.example:8554/cctv") == []
    assert detector.should_retry_with_docker_host_fallback(
        "rtsp://127.0.0.1:8554/cctv",
        "Connection refused while opening input",
    )
    assert detector.should_rewind_file_source("data/sample.mp4", 12.0, "ffmpeg failed: end of file")
    assert not detector.should_rewind_file_source("rtsp://127.0.0.1:8554/cctv", 12.0, "end of file")
