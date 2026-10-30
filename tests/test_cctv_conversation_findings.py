"""Completed goal results and qualified risks reach the existing Chat exchange."""

import asyncio
import hashlib
import json

import pytest

from cctv_operator.payloads.domain.conversation_findings import conversation_findings
from cctv_operator.payloads.domain.dashboard import operator_state
from cctv_operator.payloads.services.cctv_web_ui import CCTVWebUIService, create_operator_mcp_server


class Preview:
    def snapshot(self):
        return {"status": "live", "warning": ""}


class Server:
    def __init__(self, *args, **kwargs):
        self.tools = {}

    def tool(self, name=None, **kwargs):
        def register(fn):
            self.tools[name or fn.__name__] = getattr(fn, "__wrapped__", fn)
            return fn
        return register

    def resource(self, *args, **kwargs):
        return lambda fn: fn


def sample(**changes):
    return {"camera_id": "camera-1", "frame_seq": 1, "instruction_revision": 2,
        "monitoring_goal": "Detect a red cart", "detected_target": False,
        "observed_at": "2026-10-29T11:02:39Z", "analyzed_at": "2026-10-29T11:06:18Z",
        "scene_understanding": "A person walks beside a cart; the cart color is unclear.",
        "source_profile": "bundled_demo", "selected_count": 3, "risk_predictions": [],
        "uncertainties": ["The cart color is unclear."], "alert_decision": {"notify": False}, **changes}


def risk(**changes):
    return {"risk": "Possible contact with a cart", "severity": "medium", "confidence": .9,
        "visible_evidence": "A person approaches the parked cart in frame 2.",
        "time_horizon": "If the observed movement continues",
        "recommended_review": "Review the selected frames and the current camera view.",
        "evidence_frames": [2], **changes}


def projected(observations, revision=2, alerts=None):
    return operator_state(run_id="run-1", config={}, report={"observations": observations, "alerts": alerts or []},
        latest_frame={}, monitoring={"instruction_revision": revision}, supplemental_events=[],
        preview_status="live", preview_warning="")


def exchange(tmp_path):
    service = CCTVWebUIService(run_id="run-1", run_dir=tmp_path, config={}, preview_stream=Preview())
    server = create_operator_mcp_server(service, job_id="job-1", run_id="run-1", run_dir=tmp_path, server_factory=Server)
    return service, server


def test_notice_is_finalized_and_delivered_through_the_real_activity_watch(tmp_path):
    service, server = exchange(tmp_path)
    notice = {"type": "Operator notice", "timestamp": "2026-10-29T11:02:39Z",
        "summary": "A clearly uncovered head was observed. Review the sampled evidence."}
    digest = hashlib.sha256(f"run-1\0Operator notice\0{notice['timestamp']}\0{notice['summary']}".encode()).hexdigest()[:32]
    # Existing installations may already hold the same notice as staged.
    service._activity_store.publish_result(digest, {"message": notice["summary"]}, stage="live_activity",
        idempotency_key=f"cctv-activity:{digest}")
    service.sync_mcp_activity({"events": [notice]})
    final = service._activity_store.get_record("result", digest, include_staged=False)
    assert final["publication_state"] == "final"
    watched = asyncio.run(server.tools["watch_job_activity"]("", 0))
    activity = json.loads(watched.request_state)["activity"]
    assert activity["event_id"] == digest and activity["message"] == notice["summary"]
    assert activity["requires_review"] is True
    assert service.sync_mcp_activity({"events": [notice]}) == []


def test_first_completed_goal_result_is_deliverable_even_without_a_match(tmp_path):
    service, server = exchange(tmp_path)
    state = projected([sample()])
    service.sync_mcp_activity(state)
    watched = asyncio.run(server.tools["watch_job_activity"]("", 0))
    activity = json.loads(watched.request_state)["activity"]
    assert activity["title"] == "Monitoring result" and activity["requires_review"] is False
    for expected in ["not confirmed", "cart color is unclear", "11:02:39Z", "11:06:18Z", "Recorded demo playback"]:
        assert expected in activity["message"]
    # Restart and report rotation preserve the original delivered observation.
    restarted, _ = exchange(tmp_path)
    assert restarted.sync_mcp_activity(projected([sample(frame_seq=2, observed_at="2026-10-29T11:08:00Z")])) == []
    assert len(service._activity_store.updates(kinds=["result"], include_staged=False)["updates"]) == 1
    assert conversation_findings([], {"instruction_revision": 2}, "run-1") == []
    assert conversation_findings([sample(instruction_revision=1)], {"instruction_revision": 2}, "run-1") == []


def test_risk_without_a_goal_match_is_qualified_and_not_repeated(tmp_path):
    service, _ = exchange(tmp_path)
    observation = sample(instruction_revision=0, risk_predictions=[risk()])
    service.sync_mcp_activity(projected([observation], revision=0))
    result = service._activity_store.latest_record("result", include_staged=False)["payload"]
    assert result["title"] == "Possible risk" and result["requires_review"] is True
    assert "model forecast, not a confirmed incident" in result["message"]
    assert result["details"][-1] == {"label": "Evidence frames", "value": "2"}
    repeated = {**observation, "observed_at": "2026-10-29T11:08:00Z"}
    assert service.sync_mcp_activity(projected([repeated], revision=0)) == []
    repeated["risk_predictions"] = [risk(severity="high")]
    assert len(service.sync_mcp_activity(projected([repeated], revision=0))) == 1


@pytest.mark.parametrize("change", [{"evidence_frames": []}, {"evidence_frames": [4]},
    {"evidence_frames": [True]}, {"evidence_frames": [{}]}, {"evidence_frames": [2, 2]},
    {"confidence": .2}, {"confidence": float("nan")}, {"severity": "low"}])
def test_unsupported_forecasts_never_become_chat_risks(change):
    assert conversation_findings([sample(instruction_revision=0, risk_predictions=[risk(**change)])], {}, "run-1") == []


def test_a_confirmed_notice_does_not_duplicate_its_goal_result_and_forecast():
    assert conversation_findings([sample(alert_decision={"notify": True}, risk_predictions=[risk()])],
        {"instruction_revision": 2}, "run-1") == []


def test_conversation_identity_is_scoped_to_the_actual_run():
    first = conversation_findings([sample()], {"instruction_revision": 2}, "run-1")
    second = conversation_findings([sample()], {"instruction_revision": 2}, "run-2")
    assert first[0]["event_id"] != second[0]["event_id"]


@pytest.mark.parametrize("goal", [
    "Detect a red cart", "Watch for water on the floor", "Detect when the door is NOT closed",
    "Report if someone does not wear a safety helmet",
])
def test_goal_result_preserves_any_requested_visible_condition(goal):
    events = conversation_findings([sample(monitoring_goal=goal)], {"instruction_revision": 2}, "run-1")
    assert len(events) == 1
    assert goal in events[0]["summary"]
    assert "not confirmed" in events[0]["summary"]


def test_no_match_still_completes_the_applied_goal_analysis_status(tmp_path):
    _, server = exchange(tmp_path)
    (tmp_path / "monitoring_state.json").write_text(json.dumps({"instruction": "Detect a red cart",
        "instruction_revision": 2, "last_command_id": "goal-2"}))
    (tmp_path / "cctv_report.json").write_text(json.dumps({"observations": [sample()]}))
    status = server.tools["get_operation_status"]("goal-2")
    assert status["state"] == "completed" and status["analysis_ready"] is True
    assert status["latest_finding"] == sample()["scene_understanding"]
