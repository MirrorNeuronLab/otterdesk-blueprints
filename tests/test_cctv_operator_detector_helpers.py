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


def test_folder_source_selection_advances_across_sorted_recordings(monkeypatch, tmp_path):
    detector = _load_detector()
    folder = tmp_path / "recordings"
    folder.mkdir()
    (folder / "b.mkv").write_bytes(b"video")
    (folder / "a.mp4").write_bytes(b"video")
    (folder / "ignore.txt").write_text("not video")
    config = {"video_source": {"mode": "folder", "folder_path": str(folder)}}
    state = detector.initial_state()
    monkeypatch.setattr(detector, "probe_video_duration", lambda _path: 5.0)

    first = detector.select_media_source(config, state)
    assert first["logical_name"] == "a.mp4"
    assert first["count"] == 2
    detector.advance_media_source(state, first, sample_seconds=10.0)

    second = detector.select_media_source(config, state)
    assert second["logical_name"] == "b.mkv"
    assert state["completed_sources"] == ["a.mp4"]


def test_stream_source_is_validated_and_credentials_are_redacted():
    detector = _load_detector()
    config = {"video_source": {"mode": "stream", "uri": "rtmp://user:pass@camera.example:1935/live?token=secret"}}
    source = detector.select_media_source(config, detector.initial_state())

    assert source["mode"] == "stream"
    assert source["uri"].startswith("rtmp://user:pass@")
    assert source["logical_name"] == "rtmp://camera.example:1935/live"


def test_extract_frame_uses_cuda_decode_and_scale(monkeypatch):
    detector = _load_detector()
    commands = []

    def fake_run(command, **_kwargs):
        commands.append(command)
        Path(command[-1]).write_bytes(b"jpeg")

    monkeypatch.setattr(detector.subprocess, "run", fake_run)
    monkeypatch.setattr(detector, "ffmpeg_binary", lambda: "/usr/bin/ffmpeg")
    monkeypatch.setenv("CCTV_MEDIA_ACCELERATOR", "nvidia_cuda")

    frame, mime = detector.extract_frame("rtsp://camera.example/live", 0.0, 896)

    assert frame == b"jpeg"
    assert mime == "image/jpeg"
    command = commands[0]
    assert ["-hwaccel", "cuda"] == command[command.index("-hwaccel") : command.index("-hwaccel") + 2]
    assert ["-hwaccel_output_format", "cuda"] == command[
        command.index("-hwaccel_output_format") : command.index("-hwaccel_output_format") + 2
    ]
    assert "scale_cuda=896" in command[command.index("-vf") + 1]
