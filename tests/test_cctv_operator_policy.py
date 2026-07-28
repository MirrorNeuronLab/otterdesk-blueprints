from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = (
    ROOT
    / "cctv_operator"
    / "payloads"
    / "domain"
    / "detection_policy.py"
)
SPEC = importlib.util.spec_from_file_location(
    "cctv_operator_detection_policy", MODULE_PATH
)
assert SPEC and SPEC.loader
policy = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(policy)


def test_configured_targets_and_alert_policy_are_normalized():
    config = {
        "inputs": {
            "payload": {
                "visual_targets": [" Red backpack ", "restricted-area entry"],
                "alert_policy": {
                    "mode": "human_notice_and_slack",
                    "min_confidence": 1.5,
                    "cooldown_seconds": -4,
                    "notify_on": ["red backpack"],
                },
            }
        }
    }

    targets = policy.configured_visual_targets(config)
    alert_policy = policy.configured_alert_policy(
        config, visual_targets=targets
    )

    assert targets == ["Red backpack", "restricted-area entry"]
    assert alert_policy == {
        "mode": "human_notice_and_slack",
        "min_confidence": 1.0,
        "cooldown_seconds": 0.0,
        "notify_on": ["red backpack"],
    }
    assert (
        policy.target_prompt_text(targets)
        == "Red backpack, or restricted-area entry"
    )


def test_alert_evaluation_matches_policy_and_honors_threshold_and_cooldown():
    detection = {
        "detected_target": True,
        "confidence": 0.91,
        "detections": [
            {
                "label": "red backpack",
                "category": "unattended package",
                "activity": "left beside the doorway",
            }
        ],
        "summary": "A red backpack is beside the doorway.",
    }
    configured = {
        "mode": "human_notice_only",
        "min_confidence": 0.8,
        "cooldown_seconds": 120,
        "notify_on": ["red backpack", "person"],
    }

    first = policy.evaluate_alert(
        detection, configured, {"last_alert_wall_ts": 0}, now=500
    )
    cooling_down = policy.evaluate_alert(
        detection, configured, {"last_alert_wall_ts": 450}, now=500
    )

    assert first["notify"] is True
    assert first["matched_targets"] == ["red backpack"]
    assert first["reason"] == "notify_reviewer"
    assert cooling_down["notify"] is False
    assert cooling_down["reason"] == "cooldown_active"


def test_unconfigured_detection_does_not_notify():
    decision = policy.evaluate_alert(
        {
            "detected_target": True,
            "confidence": 0.99,
            "detections": [{"label": "forklift", "category": "equipment"}],
        },
        {
            "mode": "human_notice_only",
            "min_confidence": 0.5,
            "cooldown_seconds": 0,
            "notify_on": ["person"],
        },
        {},
        now=10,
    )

    assert decision["notify"] is False
    assert decision["reason"] == "target_not_in_notification_policy"


def test_negative_summary_mentions_do_not_match_structured_detections():
    decision = policy.evaluate_alert(
        {
            "detected_target": True,
            "confidence": 0.95,
            "detections": [
                {
                    "label": "person",
                    "category": "person",
                    "activity": "standing in the aisle",
                }
            ],
            "summary": (
                "One person is present, with no unattended package or "
                "restricted-area entry."
            ),
        },
        {
            "mode": "human_notice_only",
            "min_confidence": 0.5,
            "cooldown_seconds": 0,
            "notify_on": [
                "person",
                "unattended package",
                "restricted-area entry",
            ],
        },
        {},
        now=10,
    )

    assert decision["matched_targets"] == ["person"]
