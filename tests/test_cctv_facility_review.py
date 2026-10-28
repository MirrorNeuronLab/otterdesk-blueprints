"""Facility review and responsiveness guarantees independent of live GPU inference."""
import json
import threading
import time
from copy import deepcopy

import pytest
from PIL import Image
from test_cctv_resident_pipeline import jpeg

from cctv_operator.payloads.domain.benchmarks import Benchmarks
from cctv_operator.payloads.domain.caption_schedule import (
    CaptionSchedule,
    complete_caption,
)
from cctv_operator.payloads.domain.site_monitoring import (
    PROFILES,
    admission,
    context,
    enrich,
    notice_state,
    record_notice,
)


def batch():
    return {"selected_frames": [{"timestamp": 100., "path": "f1.jpg"}, {"timestamp": 100.25, "path": "f2.jpg"}]}


def finding(rule="blocked_route", status="observed", frames=None):
    return {"rule_id": rule, "status": status, "evidence_frames": frames or [1], "confidence": .9, "visible_evidence": "A cart spans the marked walkway in the sampled image."}


def test_periodic_audit_covers_empty_scene_without_fabricating_person(tmp_path):
    config = {"sampling": {"pre_roll_seconds": 1.5, "post_roll_seconds": .5, "scene_audit_seconds": 15}}
    schedule = CaptionSchedule(tmp_path, "run", config, Benchmarks(tmp_path))
    schedule.capture(1, 100, jpeg(), {})
    schedule.capture(2, 102, jpeg("white"), {})
    value = schedule.claim(now=102)["batch"]
    assert value["trigger"] == "scene_audit"
    record = json.loads((tmp_path / value["frame_batch_ref"]).read_text())
    assert record["candidate_gate"]["person_presence_required"] is False
    assert admission(record, config) == "periodic_scene_audit"
    with pytest.raises(ValueError, match="configured periodic"):
        admission(record, {})
    complete_caption(tmp_path, value["batch_id"], status="ok")
    schedule.capture(3, 110, jpeg(), {})
    assert schedule.claim(now=110)["batch"] is None
    schedule.capture(4, 117, jpeg(), {})
    assert schedule.claim(now=117)["batch"]["trigger"] == "scene_audit"


def test_slow_jpeg_resize_cannot_block_person_gate(tmp_path, monkeypatch):
    schedule = CaptionSchedule(tmp_path, "run", {}, Benchmarks(tmp_path))
    started, release, sampled = threading.Event(), threading.Event(), threading.Event()
    original = Image.Image.thumbnail
    def slow(self, *args, **kwargs):
        started.set()
        assert release.wait(2)
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Image.Image, "thumbnail", slow)
    worker = threading.Thread(target=schedule.capture, args=(1, 100, jpeg(), {}))
    worker.start()
    assert started.wait(2)
    person = threading.Thread(target=lambda: (schedule.person_sample(100, confirmed=True, episode=1), sampled.set()))
    person.start()
    try:
        assert sampled.wait(.5), "RF-DETR signal waited behind expensive JPEG work"
    finally:
        release.set()
        worker.join(2)
        person.join(2)
    assert schedule.person_gate["confirmed"] is True


def test_stale_pending_window_expires_instead_of_analyzing_old_scene(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {"sampling": {"post_roll_seconds": .5, "max_pending_age_seconds": 5}}, Benchmarks(tmp_path))
    schedule.person_sample(100, confirmed=True, episode=1)
    schedule.capture(1, 101, jpeg(), {})
    assert schedule.claim(now=107)["batch"] is None
    assert schedule.snapshot()["stale_windows"] == 1
    assert schedule.snapshot()["inflight"] is None


def test_automatic_and_on_demand_requests_share_admission_interval(tmp_path):
    schedule = CaptionSchedule(tmp_path, "run", {"sampling": {"post_roll_seconds": .5}, "backpressure": {"llm": {"min_interval_seconds": 5}}}, Benchmarks(tmp_path))
    schedule.person_sample(100, confirmed=True, episode=1)
    schedule.capture(1, 101, jpeg(), {})
    first = schedule.claim(now=101)["batch"]
    complete_caption(tmp_path, first["batch_id"], status="ok")
    schedule.person_sample(102, confirmed=True, episode=1)
    schedule.capture(2, 103, jpeg("white"), {})
    assert schedule.claim(force=True, now=103)["batch"] is None
    assert schedule.claim(now=106)["batch"] is not None


@pytest.mark.parametrize("profile", ["factory", "hotel"])
def test_facility_profiles_have_frame_bound_reviewable_rules(profile):
    config = {"site": {"profile": profile, "review_owner": "Duty manager"}}
    result = enrich({"site_findings": [finding()], "risk_predictions": []}, batch(), config, PROFILES[profile]["goal"], "")
    assert result["detected_target"] is True
    assert result["goal_event"]["evidence_frame"] == 1
    assert result["site_findings"][0]["review_owner"] == "Duty manager"
    assert result["site_coverage"]["unexamined_rule_ids"]
    assert "identity" in result["site_context"]["qualification"]


@pytest.mark.parametrize("change", ["bad_frame", "unknown_rule", "duplicate", "missing_head", "single_motion"])
def test_unbound_or_unsupported_facility_claims_fail(change):
    row = finding()
    if change == "bad_frame": row["evidence_frames"] = [3]
    if change == "unknown_rule": row["rule_id"] = "fraud"
    if change == "missing_head": row["rule_id"] = "uncovered_head"
    if change == "single_motion": row["rule_id"] = "vehicle_proximity"
    rows = [row, deepcopy(row)] if change == "duplicate" else [row]
    with pytest.raises(ValueError):
        enrich({"site_findings": rows}, batch(), {"site": {"profile": "factory"}}, PROFILES["factory"]["goal"], "")


def test_predictions_require_evidence_and_remain_hypotheses():
    config = {"site": {"profile": "hotel"}}
    prediction = {"risk": "A pedestrian could trip", "visible_evidence": "Cart in path", "confidence": .7, "time_horizon": "if movement continues", "severity": "medium", "recommended_review": "Inspect view"}
    with pytest.raises(ValueError, match="evidence_frames"):
        enrich({"risk_predictions": [prediction]}, batch(), config, PROFILES["hotel"]["goal"], "")
    prediction["evidence_frames"] = [1]
    result = enrich({"risk_predictions": [prediction], "site_findings": [finding(status="possible")]}, batch(), config, PROFILES["hotel"]["goal"], "")
    assert not result["detected_target"]
    assert "not a calibrated probability" in result["risk_predictions"][0]["confidence_basis"]


def test_new_rule_can_notify_without_clearing_an_uncertain_earlier_rule(monkeypatch):
    config = {"site": {"profile": "hotel"}}
    goal = PROFILES["hotel"]["goal"]
    policy = {"min_confidence": .6, "cooldown_seconds": 30}
    state = {}
    first = enrich({"site_findings": [finding()]}, batch(), config, goal, "")
    assert notice_state(first, batch(), config, policy, state, goal, "")["notified_goal"] is None
    record_notice(first, state, time.time())
    repeated = enrich({"site_findings": [finding()]}, batch(), config, goal, "")
    assert notice_state(repeated, batch(), config, policy, state, goal, "")["notified_goal"] == goal
    second = enrich({"site_findings": [finding(status="possible"), finding("person_on_floor", frames=[2])]}, batch(), config, goal, "")
    assert notice_state(second, batch(), config, policy, state, goal, "")["notified_goal"] is None
    assert second["goal_event"]["evidence_frame"] == 2
    assert "blocked_route" in state["active_site_rules"]


def test_site_zones_are_bounded_interpretation_guides_not_metric_geometry():
    config = {"site": {"profile": "hotel", "zones": [{"id": "lobby", "name": "Approved lobby view", "bounds": [0, .2, 1, .9]}]}}
    assert context(config)["zones"][0]["id"] == "lobby"
    config["site"]["zones"][0]["bounds"] = [0, 0, 2, 1]
    with pytest.raises(ValueError, match="normalized"):
        context(config)


def test_factory_worker_preserves_cited_review_queue_in_memory_and_output(monkeypatch, tmp_path, capsys, text_memory_transport):
    from test_cctv_operator_conversation import _load_detector, _run_detector
    detector = _load_detector()
    config = {"site": {"profile": "factory", "review_owner": "Shift lead"},
              "text_memory": {"enabled": True, "max_context_bytes": 49152},
              "video_source": {"profile": "bundled_demo"}}
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "warehouse"}, config=config,
        detection={"site_findings": [finding()], "summary": "A cart obstructs the path.", "confidence": .9})
    assert output["next_state"]["last_error"] is None
    observed = output["next_state"]["last_observation"]
    assert observed["site_findings"][0]["review_owner"] == "Shift lead"
    assert observed["site_coverage"]["unexamined_rule_ids"]
    notice = next(e for e in output["events"] if e["type"] == "human_notice")
    assert notice["payload"]["goal_event"]["evidence_frame"] == 1
    retained = next((tmp_path / "run/runtime_memory").glob("*-observation.json"))
    assert "Shift lead" in retained.read_text() and "not_observed" in prompts[0]


def test_compact_person_account_preserves_activity_and_frame_bound_notice(monkeypatch, tmp_path, capsys):
    from test_cctv_operator_conversation import _load_detector, _run_detector
    detector = _load_detector()
    scene = "A person stands beside the shelves with a clearly visible uncovered head."
    account = {"detected_target": True, "detections": [], "confidence": .9,
        "summary": "One person has a visibly uncovered head.", "scene_understanding": scene,
        "risk_predictions": [], "uncertainties": ["PPE requirements are not established by video."],
        "goal_event": {"start_frame": 1, "end_frame": 1, "evidence_frame": 1},
        "helmet_observations": [{"helmet_status": "not_worn", "head_visible": True,
            "evidence_frame": 1, "visible_evidence": "The uncovered head is clearly visible."}],
        "site_findings": [{**finding("uncovered_head"), "visible_evidence": "The uncovered head is clearly visible."}]}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1}, config={"site": {"profile": "factory"}}, detection=account)
    state = output["next_state"]
    assert state["last_error"] is None
    assert state["last_observation"]["activity_description"] == scene
    assert state["last_observation"]["detection_count"] == 1
    notice = next(event["payload"] for event in output["events"] if event["type"] == "human_notice")
    assert notice["goal_event"]["evidence_frame"] == 1
    assert notice["image"]["run_id"] == "test-run"
    assert notice["observed_at"] == "1970-01-01T00:00:01Z"


@pytest.mark.parametrize("profile", ["factory", "hotel"])
def test_group_at_startup_notifies_with_one_frame_and_no_hazard(profile, monkeypatch, tmp_path, capsys):
    from test_cctv_operator_conversation import ROOT, _load_detector, _run_detector
    detector = _load_detector()
    config = json.loads((ROOT / "cctv_operator/config/default.json").read_text())
    config["site"]["profile"] = profile
    config["text_memory"]["enabled"] = False
    evidence = "A group of people is visible: two helmeted people stand together beside the entrance."
    group = {**finding("group_presence"), "visible_evidence": evidence}
    result = {"site_findings": [group], "summary": evidence, "confidence": .9,
              "helmet_observations": [], "risk_predictions": []}
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "entrance"}, config=config, detection=result)
    assert output["next_state"]["last_error"] is None
    notices = [event["payload"] for event in output["events"] if event["type"] == "human_notice"]
    assert len(notices) == 1
    notice = notices[0]
    assert evidence in notice["message"]
    assert notice["risk_level"] == "low"
    assert notice["observed_at"] == "1970-01-01T00:00:01Z"
    assert notice["goal_event"]["evidence_frame"] == 1
    assert notice["image"]["run_id"] == "test-run"
    assert notice["chat_delivery"] == "otterdesk_worker_chat"
    assert "group_presence" in prompts[0]
    assert output["next_state"]["active_site_rules"] == ["group_presence"]

    repeated, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 2, "camera_id": "entrance"}, config=config,
        detection=result, state=output["next_state"])
    assert not any(event["type"] == "human_notice" for event in repeated["events"])


@pytest.mark.parametrize("status,confidence", [("not_observed", .95), ("possible", .9), ("observed", .3)])
def test_single_person_uncertain_or_low_confidence_group_stays_quiet(status, confidence, monkeypatch, tmp_path, capsys):
    from test_cctv_operator_conversation import _load_detector, _run_detector
    detector = _load_detector()
    row = {**finding("group_presence", status), "confidence": confidence,
           "visible_evidence": "Only one person can be clearly distinguished in the sampled view."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1}, config={"site": {"profile": "factory"}},
        detection={"site_findings": [row], "confidence": confidence})
    assert output["next_state"]["last_error"] is None
    assert not any(event["type"] == "human_notice" for event in output["events"])


def test_group_absence_rearms_only_when_confident_and_cooldown_has_elapsed(monkeypatch):
    from cctv_operator.payloads.domain.detection_policy import evaluate_alert
    monkeypatch.setattr(time, "time", lambda: 200.)
    config = {"site": {"profile": "factory"}}
    goal = PROFILES["factory"]["goal"]
    policy = {"min_confidence": .6, "cooldown_seconds": 120}
    state = {"active_site_rules": ["group_presence"], "site_notice_clocks": {"group_presence": 100.}}
    for status, confidence in [("possible", .9), ("not_observed", .3)]:
        row = {**finding("group_presence", status), "confidence": confidence}
        sample = enrich({"site_findings": [row]}, batch(), config, goal, "")
        notice_state(sample, batch(), config, policy, state, goal, "")
        assert state["active_site_rules"] == ["group_presence"]

    absent = enrich({"site_findings": [finding("group_presence", "not_observed")]}, batch(), config, goal, "")
    notice_state(absent, batch(), config, policy, state, goal, "")
    assert state["active_site_rules"] == []
    present = enrich({"site_findings": [finding("group_presence")]}, batch(), config, goal, "")
    decision = evaluate_alert(present, policy,
        notice_state(present, batch(), config, policy, state, goal, ""), active_goal=goal, now=200.)
    assert not decision["notify"]
    monkeypatch.setattr(time, "time", lambda: 221.)
    decision = evaluate_alert(present, policy,
        notice_state(present, batch(), config, policy, state, goal, ""), active_goal=goal, now=221.)
    assert decision["notify"]


def test_explicit_goal_keeps_group_presence_as_supplementary_material(monkeypatch, tmp_path, capsys):
    from test_cctv_operator_conversation import _load_detector, _run_detector
    detector = _load_detector()
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "instruction": "Watch only for a blocked route.", "instruction_revision": 1},
        config={"site": {"profile": "factory"}},
        detection={"detected_target": False, "site_findings": [finding("group_presence")], "confidence": .9})
    assert output["next_state"]["last_error"] is None
    assert not any(event["type"] == "human_notice" for event in output["events"])


def test_hazard_notice_does_not_consume_an_unreported_group(monkeypatch):
    monkeypatch.setattr(time, "time", lambda: 500.)
    config = {"site": {"profile": "factory"}}
    goal = PROFILES["factory"]["goal"]
    policy = {"min_confidence": .6, "cooldown_seconds": 120}
    state = {}
    findings = [finding(), {**finding("group_presence", frames=[2]),
                           "visible_evidence": "A group of people is visible near the entrance."}]
    first = enrich({"site_findings": findings}, batch(), config, goal, "")
    notice_state(first, batch(), config, policy, state, goal, "")
    record_notice(first, state, 500.)
    assert state["active_site_rules"] == ["blocked_route"]
    next_sample = enrich({"site_findings": findings}, batch(), config, goal, "")
    assert notice_state(next_sample, batch(), config, policy, state, goal, "")["notified_goal"] is None
    assert next_sample["site_notice_rule_ids"] == ["group_presence"]
    assert next_sample["goal_event"]["evidence_frame"] == 2
    assert next_sample["detection_report"].startswith("A group of people is visible")


def test_medium_severity_finding_precedes_low_severity_group_notice():
    config = {"site": {"profile": "hotel"}}
    goal = PROFILES["hotel"]["goal"]
    sample = enrich({"site_findings": [finding("group_presence"),
        {**finding("possible_spill", frames=[2]), "confidence": .8}]}, batch(), config, goal, "")
    assert sample["risk_level"] == "medium"
    assert sample["goal_event"]["evidence_frame"] == 2
    notice_state(sample, batch(), config, {"min_confidence": .6, "cooldown_seconds": 120}, {}, goal, "")
    assert sample["site_notice_rule_ids"] == ["possible_spill"]


def test_group_notice_image_and_time_follow_group_evidence_not_an_existing_hazard(monkeypatch, tmp_path, capsys):
    import base64
    from test_cctv_operator_conversation import _load_detector, _run_detector
    detector = _load_detector()
    frames = [{"timestamp": 1., "content": jpeg()}, {"timestamp": 2., "content": jpeg("white")}]
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1}, config={"site": {"profile": "factory"}}, selected=frames,
        state={**detector.initial_state(), "active_site_rules": ["blocked_route"]},
        detection={"site_findings": [finding(), {**finding("group_presence", frames=[2]),
            "visible_evidence": "A group of people is visible at the entrance."}], "confidence": .9})
    assert output["next_state"]["last_error"] is None
    notice = next(event["payload"] for event in output["events"] if event["type"] == "human_notice")
    assert notice["observed_at"] == "1970-01-01T00:00:02Z"
    assert notice["goal_event"]["evidence_frame"] == 2
    assert base64.b64decode(notice["image"]["data"]) == frames[1]["content"]
    assert "1970-01-01T00:00:02Z" in notice["image"]["caption"]


def test_stale_camera_frame_never_advances_person_episode(tmp_path):
    from cctv_operator.payloads.domain.live_monitor import LiveMonitor
    class Detector:
        variant, metadata = "fixture", {}
        def load(self): pass
        def detect(self, _): pytest.fail("stale frame reached person inference")
    class Source:
        def latest_frame(self):
            monitor.stop_event.set()
            return 1, time.time() - 20, jpeg()
    monitor = LiveMonitor(tmp_path, "run", {}, Source(), None, detector=Detector())
    monitor._person_loop()
    assert monitor.status["person_detector"] == "waiting_for_frames"
    assert monitor.episodes.state == {}


def test_new_goal_preserves_audit_admission_provenance(tmp_path):
    config = {"sampling": {"scene_audit_seconds": 15, "pre_roll_seconds": 1.5, "post_roll_seconds": .5}}
    schedule = CaptionSchedule(tmp_path, "run", config, Benchmarks(tmp_path))
    schedule.capture(1, 100, jpeg(), {})
    schedule.capture(2, 105, jpeg(), {})
    result = schedule.claim({"instruction_revision": 2, "instruction": "Inspect lobby"}, now=105)
    data = json.loads((tmp_path / result["batch"]["frame_batch_ref"]).read_text())
    assert admission(data, config) == "periodic_scene_audit"
    assert data["instruction_revision"] == 2
