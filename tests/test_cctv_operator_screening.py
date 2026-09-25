from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1] / "cctv_operator" / "payloads" / "domain"


def load_module(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_gate_requires_a_bounded_boolean_decision_and_branches():
    screening = load_module("screening")
    assert screening.branch(screening.normalize_gate({"condition_met": True, "confidence": 0.92}),
                            min_confidence=0.8) == "deep_analysis"
    assert screening.branch(screening.normalize_gate({"condition_met": False, "confidence": 0.93}),
                            min_confidence=0.8) == "no_match"
    assert screening.branch(screening.normalize_gate({"condition_met": True, "confidence": 0.57}),
                            min_confidence=0.8) == "human_review"
    with pytest.raises(ValueError):
        screening.normalize_gate({"condition_met": "yes", "confidence": 0.99})
    with pytest.raises(ValueError):
        screening.normalize_gate({"condition_met": False, "confidence": 1.5})


def test_uncertain_frame_review_is_blocking_and_rejection_is_default():
    screening = load_module("screening")
    request = screening.review_request(request_id="review-1", goal="person by door",
                                       camera_id="entrance", frame_seq=4, confidence=0.55)
    assert request["interaction_kind"] == "approval"
    assert request["blocking"] is True
    assert request["frame_seq"] == 4
    assert [option["label"] for option in request["options"]] == ["Approve", "Reject"]
    assert screening.approved({"response": {"decision": "approve"}}) is True
    assert screening.approved({"response": {"decision": "reject"}}) is False
    assert screening.approved({}) is False


def test_snapshot_manifest_uses_the_shared_conversation_widget_contract(tmp_path):
    snapshot = load_module("conversation_snapshot")
    jpeg = b"\xff\xd8" + b"jpeg-content" + b"\xff\xd9"
    source = tmp_path / "latest_analyzed_frame.jpg"
    source.write_bytes(jpeg)
    assert snapshot.publish_snapshot(tmp_path, source, run_id="run-1",
                                     camera_id="entrance", frame_seq=4)
    manifest = json.loads((tmp_path / "web" / "conversation_media.json").read_text())
    assert manifest["schema"] == "otterdesk.conversation_media.v1"
    assert manifest["run_id"] == "run-1"
    assert manifest["items"][0]["filename"] == "cctv_snapshot.jpg"
    assert manifest["items"][0]["sha256"] == hashlib.sha256(jpeg).hexdigest()
    assert (tmp_path / "web" / "cctv_snapshot.jpg").read_bytes() == jpeg
