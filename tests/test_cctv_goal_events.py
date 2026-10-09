import base64

import pytest

from cctv_operator.payloads.domain.conversation_snapshot import event_snapshot
from cctv_operator.payloads.domain.goal_events import goal_event
from cctv_operator.payloads.domain.helmet_findings import validate_helmet_goal
from cctv_operator.payloads.domain.detection_policy import DEFAULT_MONITORING_GOAL
from cctv_operator.payloads.domain.video_summary import summarize_video


def batch():
    return {"selected_frames": [{"path": f"frames/{index}.jpg", "timestamp": 1767225600 + index}
                                for index in range(1, 4)]}


@pytest.mark.parametrize("observation", [None,
    {"helmet_status": "worn", "head_visible": True, "evidence_frame": 2, "visible_evidence": "Helmet visible."},
    {"helmet_status": "uncertain", "head_visible": False, "evidence_frame": 2, "visible_evidence": "Head occluded."},
    {"helmet_status": "not_worn", "head_visible": False, "evidence_frame": 2, "visible_evidence": "Head unclear."},
    {"helmet_status": "not_worn", "head_visible": True, "evidence_frame": 1, "visible_evidence": "Uncovered head."},
])
def test_generic_person_or_unconfirmed_helmet_account_cannot_notify(observation):
    result = {"detected_target": True, "summary": "A person is visible.",
              "goal_event": {"start_frame": 1, "end_frame": 3, "evidence_frame": 2},
              "helmet_observations": [observation] if observation else [], "uncertainties": []}
    checked = validate_helmet_goal(result, DEFAULT_MONITORING_GOAL, batch())
    assert checked["detected_target"] is False and checked["goal_event"] is None
    assert checked["summary"] == result["summary"]  # Keep scene history.
    assert checked["goal_validation"] == "missing_helmet_evidence_unavailable"
    assert checked["uncertainties"]
    assert validate_helmet_goal(result, "Watch the doorway", batch()) is result


def test_missing_helmet_requires_a_visible_head_in_the_attached_frame():
    result = {"detected_target": True,
              "goal_event": {"start_frame": 1, "end_frame": 3, "evidence_frame": 2},
              "helmet_observations": [{"helmet_status": "not_worn", "head_visible": True,
                  "evidence_frame": 2, "visible_evidence": "Uncovered head visible beside the shelves."}]}
    checked = validate_helmet_goal(result, DEFAULT_MONITORING_GOAL, batch())
    assert checked["detected_target"] is True
    assert goal_event(checked, batch())["frame_path"] == "frames/2.jpg"


def test_goal_match_uses_model_selected_frame_and_capture_time(tmp_path):
    event = goal_event({"detected_target": True,
                        "goal_event": {"start_frame": 1, "end_frame": 3, "evidence_frame": 2}}, batch())
    assert event["frame_path"] == "frames/2.jpg"
    assert event["observed_at"] == "2026-01-01T00:00:02Z"
    assert event["started_at"] == "2026-01-01T00:00:01Z"
    assert event["ended_at"] == "2026-01-01T00:00:03Z"
    (tmp_path / "frames").mkdir()
    first = b"\xff\xd8first frame\xff\xd9"
    source = tmp_path / event["frame_path"]
    source.write_bytes(first)
    image = event_snapshot(tmp_path, event, run_id="run-1", camera_id="lobby", frame_seq=42)
    assert base64.b64decode(image["data"]) == first
    assert "2026-01-01T00:00:02Z" in image["caption"]
    source.write_bytes(b"\xff\xd8next frame\xff\xd9")
    event_snapshot(tmp_path, event, run_id="run-1", camera_id="lobby", frame_seq=43)
    assert first in [path.read_bytes() for path in (tmp_path / "web/events").glob("*.jpg")]
    assert base64.b64decode(image["data"]) == first


@pytest.mark.parametrize("value", [None, {}, {"start_frame": 1, "end_frame": 3, "evidence_frame": 4},
                                   {"start_frame": 2, "end_frame": 3, "evidence_frame": 1},
                                   {"start_frame": True, "end_frame": 3, "evidence_frame": 2}])
def test_match_without_valid_evidence_is_rejected(value):
    with pytest.raises(ValueError, match="goal"):
        goal_event({"detected_target": True, "goal_event": value}, batch())
    assert goal_event({"detected_target": False, "goal_event": value}, batch()) is None


def test_event_snapshot_cannot_read_outside_the_run(tmp_path):
    with pytest.raises(ValueError, match="run-relative"):
        event_snapshot(tmp_path, {"frame_path": "../outside.jpg"}, run_id="run-1", camera_id="lobby", frame_seq=1)


def test_event_snapshot_cannot_write_through_an_external_web_directory(tmp_path):
    run = tmp_path / "run"
    run.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (run / "web").symlink_to(outside, target_is_directory=True)
    (run / "frame.jpg").write_bytes(b"\xff\xd8frame\xff\xd9")
    with pytest.raises(ValueError, match="output is outside"):
        event_snapshot(run, {"frame_path": "frame.jpg", "observed_at": "2026-01-01T00:00:00Z"}, run_id="run-1", camera_id="lobby", frame_seq=1)
    assert list(outside.iterdir()) == []


def test_video_summary_aggregates_nvidia_intervals_in_chronological_order():
    report = {"observations": [
        {"observed_at": "2026-01-01T00:00:03Z", "scene_understanding": "A group stands together.",
         "capture_started_at": "2026-01-01T00:00:01Z", "capture_ended_at": "2026-01-01T00:00:03Z",
         "detected_target": True, "monitoring_goal": "group standing together", "frame_batch_ref": "batch-2",
         "risk_predictions": [{"risk": "Possible crowding", "confidence": 0.4}]},
        {"observed_at": "2026-01-01T00:00:00Z", "scene_understanding": "The room is empty."},
    ]}
    result = summarize_video(report)
    assert result["included_observations"] == 2
    assert [event["description"] for event in result["events"]] == ["The room is empty.", "A group stands together."]
    assert result["events"][1]["start_time"] == "2026-01-01T00:00:01Z"
    assert result["events"][1]["goal_matched"] is True
    assert result["continuous_coverage"] is False
    assert "A group stands together" in result["summary"]
    assert "Predictions are not observed events" in result["summary"]
    bounded = summarize_video(report, after="2026-01-01T00:00:01+00:00", before="2026-01-01T00:00:03Z")
    assert len(bounded["events"]) == 1
    assert summarize_video({}, after="2026-01-01T00:00:00Z")["status"] == "no_observations"


def test_video_summary_discloses_omitted_captions_and_rejects_ambiguous_time_bounds():
    result = summarize_video({"observations": [{"observed_at": "2026-01-01T00:00:00Z", "summary": "x" * 25_000}]})
    assert result["omitted_observations"] == 1
    assert result["events"] == []
    with pytest.raises(ValueError, match="timezone"):
        summarize_video({}, after="2026-01-01T00:00:00")
    with pytest.raises(ValueError, match="precede"):
        summarize_video({}, after="2026-01-02T00:00:00Z", before="2026-01-01T00:00:00Z")
