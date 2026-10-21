from __future__ import annotations

import json


def test_sampling_defaults_and_scene_gate_are_bounded():
    from mn_live_video_analysis_skill import (
        SamplingPolicy,
        scene_change_score,
        update_scene_gate,
    )

    policy = SamplingPolicy.from_mapping({})
    assert policy.proxy_fps == 1
    assert policy.baseline_interval_seconds == 20
    assert policy.max_model_frames == 10
    assert policy.max_calls_per_minute == 6
    assert scene_change_score(bytes([0, 10]), bytes([255, 10])) == 0.5

    state, triggered = update_scene_gate({}, 0.2, policy)
    assert triggered is False
    state, triggered = update_scene_gate(state, 0.2, policy)
    assert triggered is True
    assert state["scene_change_consecutive"] == 0


def test_live_source_redaction_removes_credentials_and_query_tokens():
    from mn_live_video_analysis_skill import redact_source_urls

    redacted = redact_source_urls(
        "decode failed for rtsp://camera-user:camera-pass@example.test/live?token=secret"
    )

    assert redacted == "decode failed for rtsp://example.test/live"


def test_frame_selection_deduplicates_and_preserves_temporal_coverage():
    from mn_live_video_analysis_skill import (
        compressed_frame_change_score,
        select_diverse_frames,
    )

    candidates = [
        {"timestamp": index, "score": index / 10, "content": f"frame-{index}".encode()}
        for index in range(12)
    ]
    candidates.insert(5, {"timestamp": 4.5, "score": 1.0, "content": b"frame-4"})

    selected = select_diverse_frames(candidates, limit=10)

    assert len(selected) == 10
    assert selected[0]["timestamp"] == 0
    assert selected[-1]["timestamp"] == 11
    assert len({item["sha256"] for item in selected}) == 10
    assert compressed_frame_change_score(b"\x00" * 100, b"\xff" * 100) == 1


def test_pending_batch_priority_coalesces_events_and_protects_on_demand():
    from mn_live_video_analysis_skill import coalesce_pending_batch

    event, reason = coalesce_pending_batch(
        {"trigger": "scene_event", "batch_id": "one"},
        {"trigger": "scene_event", "batch_id": "two"},
    )
    assert reason == "scene_event_coalesced"
    assert event["batch_id"] == "two"

    on_demand, reason = coalesce_pending_batch(
        event,
        {"trigger": "on_demand", "batch_id": "three"},
    )
    assert reason == "scene_event_replaced"
    assert on_demand["batch_id"] == "three"

    kept, reason = coalesce_pending_batch(
        on_demand,
        {"trigger": "baseline", "batch_id": "four"},
    )
    assert reason == "baseline_dropped"
    assert kept["batch_id"] == "three"


def test_steering_is_run_scoped_revisioned_and_clearable():
    from cctv_operator.payloads.domain.monitoring import (
        apply_steering_command,
        initial_monitoring_state,
    )

    state, event = apply_steering_command(
        initial_monitoring_state(),
        {
            "command_id": "command-one",
            "instruction": "  Watch   the red backpack. ",
        },
        now=10,
    )
    assert state["instruction"] == "Watch the red backpack."
    assert state["instruction_revision"] == 1
    assert event["payload"]["analyze_now"] is True

    state, event = apply_steering_command(
        state,
        {"command_id": "command-two", "clear": True, "analyze_now": False},
        now=20,
    )
    assert state["instruction"] == ""
    assert state["instruction_revision"] == 2
    assert event["payload"]["cleared"] is True


def test_monitoring_state_is_written_as_a_durable_run_artifact(tmp_path):
    from cctv_operator.payloads.domain.monitoring import (
        initial_monitoring_state,
        write_monitoring_state,
    )

    state = {
        **initial_monitoring_state(),
        "instruction": "Watch the left doorway.",
        "instruction_revision": 4,
        "last_command_id": "command-four",
        "updated_at": 42.0,
    }

    path = write_monitoring_state(tmp_path, state)

    assert path == tmp_path / "monitoring_state.json"
    assert json.loads(path.read_text()) == {
        "schema": "otterdesk.cctv_operator.monitoring_state.v1",
        **state,
    }


def test_frame_batch_is_durable_and_contains_only_artifact_metadata(tmp_path):
    from mn_live_video_analysis_skill import (
        frame_digest,
        write_frame_batch,
        write_latest_analyzed_frame,
    )

    content = b"jpeg-frame"
    selected = [
        {
            "content": content,
            "timestamp": 3.0,
            "score": 0.7,
            "sha256": frame_digest(content),
        }
    ]
    batch_path, manifest = write_frame_batch(
        tmp_path,
        batch_id="batch-one",
        trigger="on_demand",
        source={"mode": "stream", "uri": "rtsp://camera.example/live"},
        instruction="Watch the door.",
        instruction_revision=2,
        candidates=selected,
        selected=selected,
        schema="otterdesk.cctv_operator.frame_batch.v2",
    )

    persisted = json.loads(batch_path.read_text())
    assert persisted == manifest
    assert persisted["selected_frames"][0]["path"].endswith("frame-01.jpg")
    assert "content" not in json.dumps(persisted)
    assert (tmp_path / persisted["selected_frames"][0]["path"]).read_bytes() == content
    assert not (tmp_path / "latest_analyzed_frame.jpg").exists()

    latest, metadata = write_latest_analyzed_frame(
        tmp_path,
        manifest,
        model_latency_ms=42,
        schema="otterdesk.cctv_operator.latest_frame.v2",
    )
    assert latest.read_bytes() == content
    assert metadata["trigger"] == "on_demand"
    assert metadata["model_latency_ms"] == 42
