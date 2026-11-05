"""Durable account publication, capacity, time filtering and source isolation."""

import asyncio
import json
from datetime import datetime

import pytest
from mn_sdk_mcp import JobExchangeStore

from cctv_operator.payloads.domain.caption_store import CaptionStore
from cctv_operator.payloads.domain.errors import CameraStateError
from cctv_operator.payloads.domain.publication import Publisher
from test_cctv_realtime_protocol import CHUNK, make_analysis


def caption(analysis):
    analysis.session_id = "session"
    analysis.state["model"] = "Cosmos3-Edge"
    asyncio.run(analysis.caption(CHUNK))
    return analysis.store.history()["observations"][0]


def test_completed_sources_reports_and_activity_survive_reopening(tmp_path):
    analysis, _, _, _ = make_analysis(tmp_path)
    exchange = JobExchangeStore(tmp_path / "activity.sqlite3", allowed_root=tmp_path, job_id="job", run_id="run")
    publisher = Publisher(tmp_path / "outputs", analysis.store, exchange)
    analysis.publish = publisher.caption
    value = caption(analysis)
    reference = value["source_refs"][0]
    assert (tmp_path / "outputs" / reference).is_file()
    assert CHUNK["content"] in (tmp_path / "outputs/cctv_report.md").read_text()
    source = next((tmp_path / "outputs/context_sources/outputs").glob("*.md"))
    assert value["start_time"] in source.read_text()
    assert value["end_time"] in source.read_text()
    assert CHUNK["content"] in source.read_text()
    final = json.loads((tmp_path / "outputs/final_artifact.json").read_text())
    assert final["evidence"][0]["content"] == CHUNK["content"]
    assert "private-password" not in json.dumps(final)
    record = exchange.latest_record("result", include_staged=False)
    assert record["publication_state"] == "final"
    assert record["payload"]["message"] == CHUNK["content"]
    reopened = CaptionStore(analysis.store.path, job_id="job", run_id="run-2", source_id=analysis.settings.source_id)
    assert reopened.history()["observations"][0]["content"] == CHUNK["content"]
    assert reopened.history(current_run=True)["observations"] == []
    assert not list((tmp_path / "outputs").rglob("*.jpg"))
    # Core writes as container root; host synchronization reads as another user.
    for artifact in (tmp_path / "outputs").rglob("*"):
        if artifact.is_file():
            assert artifact.stat().st_mode & 0o777 == 0o644, artifact


def test_ordinary_windows_remain_saved_without_repeated_chat_updates(tmp_path):
    analysis, _, _, _ = make_analysis(tmp_path)
    exchange = JobExchangeStore(tmp_path / "activity.sqlite3", allowed_root=tmp_path, job_id="job", run_id="run")
    analysis.publish = Publisher(tmp_path / "outputs", analysis.store, exchange).caption
    caption(analysis)
    asyncio.run(analysis.caption({**CHUNK, "chunk_id": 1, "start_time": "2026-11-03T20:00:04Z", "end_time": "2026-11-03T20:00:08Z"}))
    assert analysis.store.history()["total_count"] == 2
    assert len(exchange.updates(after_revision=0, kinds=["result"], include_staged=False)["updates"]) == 1


@pytest.mark.asyncio
async def test_goal_timeline_and_chat_share_the_window_snapshot(tmp_path):
    from cctv_operator.payloads.domain.preview import Preview
    from cctv_operator.payloads.domain.window_evidence import assessment, box_coordinates
    from mn_sdk_mcp.activity import normalize_job_activity
    from test_cctv_realtime_history import coat
    analysis, _, _, _ = make_analysis(tmp_path)
    analysis.session_id, analysis.state["model"], analysis.revision = "session", "Cosmos3-Edge", 2
    analysis.settings = analysis.settings.model_copy(update={"prompt": "Find a person without a helmet."})
    preview = analysis.preview = Preview()
    start = datetime.fromisoformat(CHUNK["start_time"]).timestamp()
    frame = coat("red")
    preview._frames.extend([(start - 1, b"stale"), (start + 2, frame), (start + 60, b"future")])
    assert preview.window_frame("2026-11-01T00:00:00+00:00", "2026-11-01T00:00:04+00:00") is None
    exchange = JobExchangeStore(tmp_path / "activity.sqlite3", allowed_root=tmp_path, job_id="job", run_id="run")
    analysis.publish = Publisher(tmp_path / "outputs", analysis.store, exchange).caption
    async def review(model, instruction, *, jpeg):
        assert jpeg == frame and "without" in instruction
        return "matched", "The head is visible.", [210, 100, 620, 600]
    analysis.client.review = review
    await analysis.caption({**CHUNK, "content": '{"verdict":"not_matched","summary":"No one is in view."}'})
    await analysis.caption({**CHUNK, "chunk_id": 1, "content": '```json\n{"verdict":"matched","summary":"A person has an uncovered head."}\n```'})
    await analysis.caption({**CHUNK, "chunk_id": 2, "content": '{"verdict":"matched","summary":"A head is still uncovered."}'})
    await analysis.caption({**CHUNK, "chunk_id": 3, "content": 'No helmet is visible.\n```json\n[{"bbox_2d":[0,0,812,406]}]\n```'})
    all_windows = analysis.snapshot()
    assert len(all_windows["captions"]) == 4 and all_windows["match_count"] == 2
    match = all_windows["goal_matches"][0]
    assert match["summary"] == "A person has an uncovered head."
    assert match["snapshot"]["bbox_2d"] == [210, 100, 620, 600]
    assert analysis.store.frame(match["id"]) == frame
    assert (tmp_path / "outputs" / match["snapshot"]["source_ref"]).read_bytes() == frame
    assert len(exchange.updates(after_revision=0, kinds=["result"], include_staged=False)["updates"]) == 2
    activity = normalize_job_activity(exchange.latest_record("result", include_staged=False)["payload"])
    assert activity["occurred_at"] == match["end_time"] and activity["image"]["title"] == "Window snapshot"
    assert activity["details"][1]["value"] == analysis.settings.prompt
    assert all_windows["captions"][-1]["content"] == "No helmet is visible."
    assert assessment('{"summary":"Unsure","verdict":true}')[0] == "uncertain"
    assert not any(box_coordinates(value) for value in [[0, 0, 1000, 1000], [2, 3, 1, 8], [0, 0, 700, 1100], [True, 5, 20, 80]])
    analysis.revision = 3
    assert analysis.snapshot()["goal_matches"] == []
    await analysis.client.http.aclose()


def test_history_is_job_camera_scoped_and_has_explicit_capture_bounds(tmp_path):
    analysis, _, _, _ = make_analysis(tmp_path)
    caption(analysis)
    other_source = CaptionStore(analysis.store.path, job_id="job", run_id="run", source_id="different-camera")
    assert other_source.history()["observations"] == []
    with pytest.raises(ValueError, match="another Job"):
        CaptionStore(analysis.store.path, job_id="other-job", run_id="run", source_id=analysis.settings.source_id)
    assert len(analysis.store.history(after="2026-11-03T15:00:00-05:00", before="2026-11-03T20:00:04Z")["observations"]) == 1
    assert analysis.store.history(after="2026-11-03T20:01:00Z")["observations"] == []
    with pytest.raises(ValueError, match="timezone"):
        analysis.store.history(after="2026-11-03T20:00:00")
    with pytest.raises(ValueError, match="before it starts"):
        analysis.store.history(after="2026-11-04T00:00:00Z", before="2026-11-03T00:00:00Z")


def test_capacity_never_deletes_evidence_and_duplicate_payload_conflicts_fail(tmp_path):
    analysis, _, _, _ = make_analysis(tmp_path)
    value = caption(analysis)
    value.pop("revision")
    assert not analysis.store.append({**value, "received_at": "later transport receipt"})
    with pytest.raises(ValueError, match="different content"):
        analysis.store.append({**value, "content": "Different content"})
    analysis.store.max_records = 1
    with pytest.raises(CameraStateError, match="storage is full"):
        analysis.store.append({**value, "id": "another"})
    assert analysis.store.history()["total_count"] == 1


@pytest.mark.parametrize("changes", [{"end_time": "2026-11-03T19:00:00Z"}, {"vlm_latency_ms": float("nan")},
                                     {"content": "<think>private reasoning</think>"}, {"finish_reason": "length"}])
def test_invalid_incomplete_or_private_content_never_publishes(tmp_path, changes):
    analysis, _, _, published = make_analysis(tmp_path)
    analysis.session_id = "session"
    analysis.state["model"] = "Cosmos3-Edge"
    with pytest.raises(ValueError):
        asyncio.run(analysis.caption({**CHUNK, **changes}))
    assert not published
    assert analysis.store.history()["observations"] == []
