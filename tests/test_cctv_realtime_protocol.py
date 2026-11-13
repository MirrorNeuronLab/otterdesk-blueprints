"""Real-time caption protocol and ownership; no camera or live model required."""

import asyncio
import json

import httpx
import pytest

from cctv_operator.payloads.domain.analysis import Analysis
from cctv_operator.payloads.domain.caption_store import CaptionStore
from cctv_operator.payloads.domain.realtime_client import VLMClient, sse_data
from cctv_operator.payloads.domain.settings import CameraSettings, camera_settings, service_url


CHUNK = {"chunk_id": 0, "content": "A person walks along the aisle.",
         "start_time": "2026-11-03T20:00:00Z", "end_time": "2026-11-03T20:00:04Z",
         "vlm_latency_ms": 890.2, "chunk_latency_ms": 4200}


class CaptionStream(httpx.AsyncByteStream):
    def __init__(self, chunks=None, raw=None):
        self.chunks, self.raw = [CHUNK] if chunks is None else chunks, raw
        self.sent = asyncio.Event()
        self.closed = False

    async def __aiter__(self):
        yield self.raw or ("data: " + json.dumps({"request_id": "request-1", "chunk_responses": self.chunks}) + "\n\n").encode()
        self.sent.set()
        await asyncio.Event().wait()

    async def aclose(self):
        self.closed = True


def make_analysis(tmp_path, handler=None, *, chunks=None, raw=None):
    calls, streams = [], []
    async def transport(request):
        calls.append((request.method, request.url.path, dict(request.url.params)))
        if handler:
            response = await handler(request)
            if response is not None:
                return response
        if request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": "Cosmos3-Edge"}]})
        if request.url.path == "/v1/streams/add":
            return httpx.Response(200, json={"results": [{"id": "stream-1"}]})
        if request.method == "POST" and request.url.path == "/v1/generate_captions":
            stream = CaptionStream(chunks, raw)
            streams.append(stream)
            return httpx.Response(200, headers={"x-request-id": "request-1"}, stream=stream)
        return httpx.Response(200, text="ok")
    http = httpx.AsyncClient(base_url="http://vlm/", transport=httpx.MockTransport(transport))
    client = VLMClient("http://vlm", http)
    settings = CameraSettings(uri="rtsp://user:private-password@camera/stream?token=private-token")
    store = CaptionStore(tmp_path / "captions.sqlite3", job_id="job", run_id="run", source_id=settings.source_id)
    published, states = [], []
    analysis = Analysis(client, settings, store, published.append, states.append)
    return analysis, calls, streams, published


async def wait_for(predicate):
    async with asyncio.timeout(3):
        while not predicate():
            await asyncio.sleep(0)


@pytest.mark.parametrize("uri", ["file:///video.mp4", "http://camera", "rtsp://", "rtsp://camera:invalid/live", "rtsp://camera/live\nsecret", "rtsp://camera/live#fragment"])
def test_invalid_camera_configuration_never_echoes_input(uri):
    with pytest.raises(ValueError) as failure:
        camera_settings({"video_source": {"uri": uri}})
    assert uri not in str(failure.value)


def test_public_settings_exclude_address_and_identity_excludes_credentials():
    first = CameraSettings(uri="rtsp://user:secret@camera/stream?token=one")
    second = CameraSettings(uri="rtsp://other:password@camera/stream?token=one")
    assert first.source_id == second.source_id
    assert first.source_id != CameraSettings(uri="rtsp://camera/stream?token=two").source_id
    assert "uri" not in first.model_dump()
    assert "secret" not in repr(first)
    for invalid in ["http://user:secret@vlm", "http://vlm/path", "file:///tmp"]:
        with pytest.raises(ValueError):
            service_url(invalid)


@pytest.mark.asyncio
async def test_multiline_sse_comments_final_record_and_capacity():
    async def lines():
        for line in [": heartbeat", "data: one", "data:two", "", "event: caption", "data: final"]:
            yield line
    assert [item async for item in sse_data(lines())] == ["one\ntwo", "final"]
    with pytest.raises(ValueError, match="size limit"):
        [item async for item in sse_data(lines(), max_bytes=2)]


@pytest.mark.asyncio
async def test_candidate_review_uses_original_jpeg_and_the_existing_nvidia_model():
    import base64
    from test_cctv_realtime_history import coat
    jpeg = coat("red")
    def transport(request):
        assert request.url.path == "/v1/chat/completions"
        body = json.loads(request.content)
        assert body["model"] == "camera-model"
        text, image = body["messages"][-1]["content"]
        assert "red coat" in text["text"]
        assert base64.b64decode(image["image_url"]["url"].split(",", 1)[1]) == jpeg
        return httpx.Response(200, json={"choices":[{"finish_reason":"stop", "message":{"content":
            '{"verdict":"matched","summary":"A red coat is visible.","bbox_2d":[12,34,400,840]}'}}]})
    async with httpx.AsyncClient(base_url="http://vlm/", transport=httpx.MockTransport(transport)) as http:
        assert await VLMClient("http://vlm", http).review("camera-model", "red coat", jpeg=jpeg) == (
            "matched", "A red coat is visible.", [12,34,400,840])


@pytest.mark.asyncio
async def test_real_payload_deduplication_and_ordered_request_cleanup(tmp_path):
    payloads = []
    async def handler(request):
        if request.url.path == "/v1/generate_captions" and request.method == "POST":
            payloads.append(json.loads(request.content))
    analysis, calls, streams, published = make_analysis(tmp_path, handler, chunks=[CHUNK, CHUNK])
    await analysis.start()
    await wait_for(lambda: len(published) == 1)
    payload = payloads[0]
    assert payload["model"] == "Cosmos3-Edge"
    assert payload["chunk_duration"] == 4
    assert payload["num_frames_per_second_or_fixed_frames_chunk"] == 8
    assert payload["max_tokens"] == 192
    assert payload["enable_audio"] is payload["enable_reasoning"] is False
    assert len(analysis.snapshot()["captions"]) == 1
    assert "private-password" not in json.dumps(analysis.snapshot())
    assert "private-token" not in json.dumps(analysis.snapshot())
    await analysis.stop()
    assert streams[0].closed
    assert calls[-2:] == [("DELETE", "/v1/generate_captions/stream-1", {"request_id": "request-1"}),
                          ("DELETE", "/v1/streams/delete/stream-1", {})]
    assert analysis.store.state("active_request") is None
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_stop_during_registration_recovers_ownership_before_cleanup(tmp_path):
    entered, release = asyncio.Event(), asyncio.Event()
    async def handler(request):
        if request.url.path == "/v1/streams/add":
            entered.set()
            await release.wait()
    analysis, calls, _, _ = make_analysis(tmp_path, handler)
    await analysis.start()
    await entered.wait()
    stop = asyncio.create_task(analysis.stop())
    await asyncio.sleep(0)
    assert not stop.done()
    release.set()
    await stop
    assert calls[-1][1] == "/v1/streams/delete/stream-1"
    assert analysis.store.state("active_request") is None
    assert analysis.state["status"] == "stopped"
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_immediate_stop_cannot_orphan_a_registration(tmp_path):
    analysis, calls, _, _ = make_analysis(tmp_path)
    await analysis.start()
    await analysis.stop()
    assert not any(path == "/v1/streams/add" for _, path, _ in calls)
    assert analysis.store.state("active_request") is None
    await analysis.client.http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("raw", [b'data: invalid-json\n\n', b'data: {"error":"rtsp://user:secret@camera"}\n\n', b'data: [DONE]\n\n'])
async def test_upstream_failures_are_explicit_redacted_and_release_stream(tmp_path, raw):
    analysis, calls, _, published = make_analysis(tmp_path, raw=raw)
    await analysis.start()
    await analysis.task
    assert analysis.state["status"] == "error"
    assert "secret" not in analysis.state["error"]
    assert not published
    assert calls[-1][1] == "/v1/streams/delete/stream-1"
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_failed_cleanup_is_durable_and_fences_new_registration(tmp_path):
    async def handler(request):
        if request.method == "DELETE":
            return httpx.Response(500)
    analysis, calls, _, published = make_analysis(tmp_path, handler)
    await analysis.start()
    await wait_for(lambda: bool(published))
    with pytest.raises(RuntimeError, match="not fully released"):
        await analysis.stop()
    assert analysis.store.state("active_request")["stream_id"] == "stream-1"
    before = sum(path == "/v1/streams/add" for _, path, _ in calls)
    with pytest.raises(httpx.HTTPStatusError):
        await analysis.start()
    assert sum(path == "/v1/streams/add" for _, path, _ in calls) == before
    await analysis.client.http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("message", ["No such resource stream-1", "stream-1 already deleted because of age out policy"])
@pytest.mark.parametrize("phase", ["caption", "stream"])
async def test_nvidia_missing_stream_after_server_restart_reconciles_saved_lease(tmp_path, message, phase):
    async def handler(request):
        path = "/v1/generate_captions/stream-1" if phase == "caption" else "/v1/streams/delete/stream-1"
        if request.method == "DELETE" and request.url.path == path:
            return httpx.Response(400, json={"code": "BadParameter", "message": message})
    analysis, calls, _, published = make_analysis(tmp_path, handler)
    analysis.store.set_state("active_request", {"stream_id": "stream-1", "request_id": "old-request", "origin": "http://vlm"})
    await analysis.start()
    await wait_for(lambda: bool(published))
    assert calls[0] == ("DELETE", "/v1/generate_captions/stream-1", {"request_id": "old-request"})
    assert calls[1 if phase == "caption" else 2][1] == "/v1/ready"
    await analysis.stop()
    assert analysis.store.state("active_request") is None
    await analysis.client.http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"code": "BadParameter", "message": "Invalid request"},
    {"code": "BadParameter", "message": "No such resource another-stream"},
    {"code": "InternalError", "message": "No such resource stream-1"},
    {"code": "BadParameter", "message": "No such live-stream stream-1"},
])
async def test_other_nvidia_400_errors_keep_the_ownership_fence(tmp_path, body):
    async def handler(request):
        if request.method == "DELETE":
            return httpx.Response(400, json=body)
    analysis, calls, _, _ = make_analysis(tmp_path, handler)
    lease = {"stream_id": "stream-1", "request_id": "old-request", "origin": "http://vlm"}
    analysis.store.set_state("active_request", lease)
    with pytest.raises(httpx.HTTPStatusError):
        await analysis.start()
    assert analysis.store.state("active_request") == lease
    assert not any(path == "/v1/streams/add" for _, path, _ in calls)
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_unknown_registration_after_crash_cannot_open_another_stream(tmp_path):
    analysis, calls, _, _ = make_analysis(tmp_path)
    analysis.store.set_state("active_request", {"registration_pending": True})
    with pytest.raises(ValueError, match="unknown outcome"):
        await analysis.start()
    assert calls == []
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_goal_change_serializes_cleanup_keeps_history_and_deduplicates_receipt(tmp_path):
    analysis, calls, _, published = make_analysis(tmp_path)
    await analysis.start()
    await wait_for(lambda: bool(published))
    receipt = await analysis.change_goal("change-1", "Watch when the door is NOT closed.")
    assert receipt["state"] == "completed"
    assert receipt["analysis_ready"] is False
    await wait_for(lambda: len(published) == 2)
    assert published[-1]["instruction"] == "Watch when the door is NOT closed."
    assert published[-1]["instruction_revision"] == 1
    assert len(analysis.snapshot()["captions"]) == 2
    assert await analysis.change_goal("change-1", "Watch when the door is NOT closed.") == receipt
    with pytest.raises(ValueError, match="another monitoring change"):
        await analysis.change_goal("change-1", "Different goal")
    registrations = [i for i, (_, path, _) in enumerate(calls) if path == "/v1/streams/add"]
    assert calls[registrations[1] - 1][1] == "/v1/models"
    assert any(path == "/v1/streams/delete/stream-1" for _, path, _ in calls[:registrations[1]])
    await analysis.stop()
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_completed_caption_request_still_requires_stream_deletion_before_recovery(tmp_path):
    async def handler(request):
        if request.method == "DELETE" and request.url.params.get("request_id") == "old-request":
            return httpx.Response(400, json={"code": "InvalidParameterValue", "message":
                "No active caption request old-request for live stream stream-1"})
    analysis, calls, _, published = make_analysis(tmp_path, handler)
    analysis.store.set_state("active_request", {"stream_id": "stream-1", "request_id": "old-request", "origin": "http://vlm"})
    await analysis.start()
    await wait_for(lambda: bool(published))
    assert calls[:3] == [
        ("DELETE", "/v1/generate_captions/stream-1", {"request_id": "old-request"}),
        ("DELETE", "/v1/streams/delete/stream-1", {}),
        ("GET", "/v1/ready", {}),
    ]
    await analysis.stop()
    assert analysis.store.state("active_request") is None
    await analysis.client.http.aclose()


@pytest.mark.asyncio
@pytest.mark.parametrize("code,message,request_id", [
    ("BadParameter", "No active caption request old-request for live stream stream-1", "old-request"),
    ("InvalidParameterValue", "No active caption request other-request for live stream stream-1", "old-request"),
    ("InvalidParameterValue", "No active caption request old-request for live stream other-stream", "old-request"),
    ("InvalidParameterValue", "No active caption request None for live stream stream-1", None),
])
async def test_absent_caption_receipt_must_match_both_saved_identities(tmp_path, code, message, request_id):
    async def handler(request):
        if request.method == "DELETE":
            return httpx.Response(400, json={"code": code, "message": message})
    analysis, calls, _, _ = make_analysis(tmp_path, handler)
    lease = {"stream_id": "stream-1", "request_id": request_id, "origin": "http://vlm"}
    analysis.store.set_state("active_request", lease)
    with pytest.raises(httpx.HTTPStatusError):
        await analysis.start()
    assert analysis.store.state("active_request") == lease
    assert len(calls) == 1
    await analysis.client.http.aclose()


@pytest.mark.asyncio
async def test_absent_caption_request_does_not_bypass_failed_stream_deletion(tmp_path):
    async def handler(request):
        if request.method == "DELETE" and request.url.path.startswith("/v1/generate_captions/"):
            return httpx.Response(400, json={"code": "InvalidParameterValue", "message":
                "No active caption request old-request for live stream stream-1"})
        if request.method == "DELETE":
            return httpx.Response(500)
    analysis, calls, _, _ = make_analysis(tmp_path, handler)
    lease = {"stream_id": "stream-1", "request_id": "old-request", "origin": "http://vlm"}
    analysis.store.set_state("active_request", lease)
    with pytest.raises(httpx.HTTPStatusError):
        await analysis.start()
    assert analysis.store.state("active_request") == lease
    assert not any(path == "/v1/streams/add" for _, path, _ in calls)
    await analysis.client.http.aclose()
