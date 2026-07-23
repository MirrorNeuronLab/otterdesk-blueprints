from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
DETECTOR_PATH = (
    ROOT
    / "cctv_operator"
    / "payloads"
    / "agents"
    / "visual_detector"
    / "scripts"
    / "analyze_video_frame.py"
)


def _load_detector():
    original_path = list(sys.path)
    original_domain_modules = {
        key: value
        for key, value in sys.modules.items()
        if key == "domain" or key.startswith("domain.")
    }
    for key in original_domain_modules:
        sys.modules.pop(key, None)
    spec = importlib.util.spec_from_file_location("cctv_operator_detector_helpers", DETECTOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path[:] = original_path
        for key in list(sys.modules):
            if key == "domain" or key.startswith("domain."):
                sys.modules.pop(key, None)
        sys.modules.update(original_domain_modules)
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


def test_detector_reads_only_run_relative_finalized_frame_batches(
    monkeypatch, tmp_path
):
    detector = _load_detector()
    batch_dir = tmp_path / "frame_batches" / "batch-1"
    batch_dir.mkdir(parents=True)
    (batch_dir / "frame-01.jpg").write_bytes(b"selected-jpeg")
    (batch_dir / "batch.json").write_text(
        json.dumps(
            {
                "selected_frames": [
                    {
                        "path": "frame_batches/batch-1/frame-01.jpg",
                        "timestamp": 1.0,
                    }
                ]
            }
        )
    )
    monkeypatch.setenv("MN_RUN_DIR", str(tmp_path))

    batch, frames = detector.load_frame_batch(
        "frame_batches/batch-1/batch.json"
    )

    assert batch["selected_frames"][0]["timestamp"] == 1.0
    assert frames == [b"selected-jpeg"]
    with pytest.raises(ValueError, match="run-relative"):
        detector.load_frame_batch("../outside.json")


def test_detector_uses_vision_model_defaults(monkeypatch):
    detector = _load_detector()
    monkeypatch.delenv("MN_LLM_RUNTIME_MODEL", raising=False)

    assert detector._normalize_vlm_model("medium") == "nemotron3"
    assert detector._normalize_vlm_model("nemotron3") == "nemotron3"

    monkeypatch.setenv("MN_LLM_RUNTIME_MODEL", "docker.io/ai/nemotron3:latest")
    assert detector._normalize_vlm_model("docker.io/ai/nemotron3:latest") == "nemotron3"


def test_openai_vlm_uses_portable_openai_fields_and_normalizes_model_variants(monkeypatch):
    detector = _load_detector()
    captured = {}
    model_content = {
        "detected": True,
        "detected_target": "equipment",
        "detection_count": 1,
        "detections": [
            {
                "label": "machine",
                "category": "equipment",
                "color": "blue",
                "position": "center",
                "activity": "stationary",
                "confidence": 0.91,
            }
        ],
        "summary": "One machine is visible.",
        "risk_level": "low",
    }

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps({"choices": [{"message": {"content": json.dumps(model_content)}}]}).encode()

    def fake_urlopen(request, timeout):
        captured.update(json.loads(request.data.decode()))
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("MN_VLM_PROVIDER", "docker_model_runner")
    monkeypatch.setenv("MN_VLM_API_BASE", "http://model.example/engines/v1")
    monkeypatch.setenv("MN_VLM_MODEL", "vision-model")
    monkeypatch.delenv("MN_VLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("MN_LLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    monkeypatch.delenv("MN_VLM_THINK", raising=False)
    monkeypatch.delenv("OLLAMA_THINK", raising=False)
    monkeypatch.setattr(detector.urllib.request, "urlopen", fake_urlopen)

    result = detector.call_ollama(b"jpeg", "inspect the frame")

    assert "chat_template_kwargs" not in captured
    assert captured["max_tokens"] == 900
    assert captured["url"] == "http://model.example/engines/v1/chat/completions"
    assert result["detected_target"] is True
    assert result["confidence"] == 0.91


def test_litellm_vlm_preserves_v1_openai_endpoint(monkeypatch):
    detector = _load_detector()
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {"choices": [{"message": {"content": '{"detected": false}'}}]}
            ).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setenv("MN_VLM_PROVIDER", "litellm")
    monkeypatch.setenv("MN_VLM_API_BASE", "http://mn-litellm-proxy:4000/v1")
    monkeypatch.setenv("MN_VLM_MODEL", "docker.io/ai/nemotron3:latest")
    monkeypatch.setattr(detector.urllib.request, "urlopen", fake_urlopen)

    result = detector.call_ollama(b"jpeg", "inspect the frame")

    assert captured["url"] == "http://mn-litellm-proxy:4000/v1/chat/completions"
    assert result["detected"] is False
