"""CCTV interpretation policy; transport and JSON repair now live in SDK tests.

Native model selection/media behavior is covered by test_cctv_native_vision_model;
frame provenance and effect/recovery are exercised through the real block engine.
"""
import importlib
from pathlib import Path
import sys


def _policy():
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "cctv_operator/payloads"))
    return importlib.import_module("domain.visual_detection")


def test_normalize_detection_accepts_visible_color():
    detector = _policy()

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



def test_detection_report_list_becomes_readable_conversation_text():
    detector = _policy()
    result = detector.normalize_detection({
        "detected": True,
        "detection_report": ["A person is near the entrance.", {"raw": "ignored"}, "An object is on the floor."],
    })
    assert result["detection_report"] == "A person is near the entrance. An object is on the floor."
