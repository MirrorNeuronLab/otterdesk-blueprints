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
