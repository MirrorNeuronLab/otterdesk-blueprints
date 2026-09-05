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

    assert detector._normalize_vlm_model("medium") == "nemotron3:q4_K_M"
    assert detector._normalize_vlm_model("nemotron3") == "nemotron3:q4_K_M"
    assert detector._normalize_vlm_model("nemotron3:q4_K_M") == "nemotron3:q4_K_M"
    assert (
        detector._normalize_vlm_model("docker.io/ai/nemotron3:q4_K_M")
        == "nemotron3:q4_K_M"
    )

    monkeypatch.setenv("MN_LLM_RUNTIME_MODEL", "docker.io/ai/nemotron3:latest")
    assert (
        detector._normalize_vlm_model("docker.io/ai/nemotron3:latest")
        == "nemotron3:q4_K_M"
    )


def test_dmr_vlm_disables_reasoning_and_normalizes_model_variants(monkeypatch):
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
    monkeypatch.setenv("MN_VLM_MODEL", "nemotron3:q4_K_M")
    monkeypatch.delenv("MN_VLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("MN_LLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("OLLAMA_NUM_PREDICT", raising=False)
    monkeypatch.delenv("MN_VLM_THINK", raising=False)
    monkeypatch.delenv("OLLAMA_THINK", raising=False)
    monkeypatch.setattr(detector.urllib.request, "urlopen", fake_urlopen)

    result = detector.call_ollama(b"jpeg", "inspect the frame")

    assert captured["chat_template_kwargs"] == {"enable_thinking": False}
    assert captured["thinking_budget_tokens"] == 0
    assert captured["max_tokens"] == 900
    assert captured["messages"][0]["content"][0]["text"].startswith(
        "/no_think\ninspect the frame"
    )
    assert captured["url"] == "http://model.example/engines/v1/chat/completions"
    assert result["detected_target"] is True
    assert result["confidence"] == 0.91


def test_managed_dmr_vlm_uses_lazy_runtime_model_access(monkeypatch):
    detector = _load_detector()
    captured = {}

    def fake_runtime_request(purpose, model, path, payload, **kwargs):
        captured.update(
            {
                "purpose": purpose,
                "model": model,
                "path": path,
                "payload": payload,
                **kwargs,
            }
        )
        return {
            "choices": [
                {
                    "message": {
                        "content": '{"detected": true, "confidence": 0.88}'
                    }
                }
            ]
        }

    monkeypatch.setenv("MN_RUNTIME_MODEL_MANAGED", "1")
    monkeypatch.setenv("MN_VLM_PROVIDER", "docker_model_runner")
    monkeypatch.setenv("MN_VLM_API_BASE", "auto")
    monkeypatch.setenv("MN_VLM_MODEL", "nemotron3:q4_K_M")
    monkeypatch.setattr(
        detector, "runtime_model_json_request", fake_runtime_request
    )

    result = detector.call_ollama(b"jpeg", "inspect the frame")

    assert captured["purpose"] == "vlm"
    assert captured["model"] == "nemotron3:q4_K_M"
    assert captured["path"] == "/chat/completions"
    assert captured["provider"] == "docker_model_runner"
    assert captured["api_base"] == "auto"
    assert captured["payload"]["chat_template_kwargs"] == {
        "enable_thinking": False
    }
    assert captured["payload"]["thinking_budget_tokens"] == 0
    assert captured["structured_output"] is True
    assert captured["required_capabilities"] == (
        "image_input",
        "structured_output",
    )
    assert captured["payload"]["messages"][0]["content"][0]["text"].startswith(
        "/no_think\ninspect the frame"
    )
    assert result["detected"] is True
    assert result["confidence"] == 0.88


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
        captured["payload"] = json.loads(request.data.decode())
        return FakeResponse()

    monkeypatch.setenv("MN_VLM_PROVIDER", "litellm")
    monkeypatch.setenv("MN_VLM_API_BASE", "http://mn-litellm-proxy:4000/v1")
    monkeypatch.setenv("MN_VLM_MODEL", "docker.io/ai/nemotron3:q4_K_M")
    monkeypatch.setattr(detector.urllib.request, "urlopen", fake_urlopen)

    result = detector.call_ollama(b"jpeg", "inspect the frame")

    assert captured["url"] == "http://mn-litellm-proxy:4000/v1/chat/completions"
    assert captured["payload"]["model"] == "nemotron3:q4_K_M"
    assert "chat_template_kwargs" not in captured["payload"]
    assert result["detected"] is False


def test_dmr_vlm_rejects_reasoning_only_response(monkeypatch):
    detector = _load_detector()

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self):
            return json.dumps(
                {
                    "choices": [
                        {
                            "finish_reason": "length",
                            "message": {
                                "content": "",
                                "reasoning_content": "I can see three people.",
                            },
                        }
                    ]
                }
            ).encode()

    monkeypatch.setenv("MN_VLM_PROVIDER", "docker_model_runner")
    monkeypatch.setattr(detector.urllib.request, "urlopen", lambda *_args, **_kwargs: FakeResponse())

    with pytest.raises(
        RuntimeError,
        match=r"finish_reason=length, reasoning_only=true",
    ):
        detector.call_ollama(b"jpeg", "inspect the frame")


def test_normalize_detection_accepts_visible_color():
    detector = _load_detector()

    result = detector.normalize_detection(
        {
            "detected": True,
            "detections": [
                {
                    "label": "person",
                    "category": "human",
                    "visible_color": "dark clothing",
                    "confidence": 0.9,
                }
            ],
        }
    )

    assert result["detections"][0]["color"] == "dark clothing"
