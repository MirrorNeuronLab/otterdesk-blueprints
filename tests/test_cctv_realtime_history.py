"""Camera history write/read contract. The opt-in gate uses real model weights and native Membrane."""

import asyncio
import hashlib
import io
import os
import socket
import subprocess
import time
from datetime import datetime, timedelta, timezone

import grpc
import pytest
from PIL import Image, ImageDraw

from cctv_operator.payloads.domain.caption_store import CaptionStore
from cctv_operator.payloads.domain.video_questions import VideoQuestions
from cctv_operator.payloads.domain.visual_history import VisualHistory, search_interval

QUESTION = "tell me did you find anyone wearing red coat in past hour"
CONFIG = {"source_context": {"enabled": True}}


def coat(color):
    image = Image.new("RGB", (224, 224), "#dddddd")
    draw = ImageDraw.Draw(image)
    draw.ellipse((90, 15, 134, 59), fill="#876249")
    draw.polygon([(80,60),(63,69),(35,125),(51,136),(77,101),(75,164),(148,164),
                  (145,101),(172,136),(188,125),(161,69),(144,60)], fill=color)
    draw.rectangle((80,165,106,217), fill="#292929")
    draw.rectangle((115,165,142,217), fill="#292929")
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return buffer.getvalue()


def save(store, identity, start, color=None):
    frame = coat(color) if color else None
    caption = {"id": identity, "run_id": store.run_id, "start_time": start.isoformat(),
               "end_time": (start + timedelta(seconds=4)).isoformat(), "source_refs": [f"captions/{identity}.json"],
               "content": "A person is standing."}
    if frame:
        caption["snapshot"] = {"received_at": start.isoformat(), "sha256": hashlib.sha256(frame).hexdigest()}
    store.append(caption, frame)
    return caption


class Embeddings:
    metadata = {"model": "test", "tokenizer": "test"}
    vector = [1.0] + [0.0] * 767

    def embed(self, chunks):
        return {"vectors": [{**c, "end_byte": c["start_byte"] + len(c["text"].encode()), "values": self.vector}
                            for c in chunks]}

    def embed_media(self, media):
        assert media.data == coat("red")
        return self.embed_query("")

    def embed_query(self, question):
        return {**self.metadata, "vector": self.vector}


def test_retry_requires_image_ack_and_reopens_across_runs(tmp_path, text_memory_transport, monkeypatch):
    store = CaptionStore(tmp_path / "camera.db", job_id="test", run_id="run-1", source_id="camera")
    now = datetime.now(timezone.utc)
    save(store, "red", now - timedelta(minutes=45), "red")
    encoder = Embeddings()
    history = VisualHistory(CONFIG, store, embeddings=encoder)
    with monkeypatch.context() as m:
        def unavailable(media):
            raise ConnectionError("encoder offline")
        m.setattr(encoder, "embed_media", unavailable)
        with pytest.raises(ConnectionError):
            history.index_next()
    assert store.index_counts(history.model) == (1, 0)
    assert history.search(QUESTION, *search_interval(QUESTION, clock=now))["observations"] == []
    assert not history.index_next()
    retry_time = time.time() + 31
    monkeypatch.setattr(time, "time", lambda: retry_time)
    assert history.index_next()
    assert store.index_counts(history.model) == (1, 1)
    next_run = CaptionStore(store.path, job_id="test", run_id="run-2", source_id="camera")
    assert not VisualHistory(CONFIG, next_run, embeddings=encoder).index_next()
    other = CaptionStore(store.path, job_id="test", run_id="run-2", source_id="elsewhere")
    assert not VisualHistory(CONFIG, other, embeddings=encoder).search(QUESTION, "", "")["total"]


@pytest.mark.asyncio
async def test_questions_freeze_time_and_review_only_retrieved_evidence(tmp_path, text_memory_transport):
    store = CaptionStore(tmp_path / "camera.db", job_id="test", run_id="run", source_id="camera")
    now = datetime.now(timezone.utc)
    save(store, "old", now - timedelta(hours=2), "red")
    save(store, "inside", now - timedelta(minutes=45), "red")
    history = VisualHistory(CONFIG, store, embeddings=Embeddings())
    assert history.index_next() and history.index_next()
    reviews = []
    class VLM:
        async def review(self, model, question, *, jpeg, caption):
            reviews.append(question)
            return "matched", "The sample shows someone wearing a red coat.", None
    questions = VideoQuestions(history, VLM(), lambda: "test-model")
    question = "Did a person wear a red coat in the past hour?"
    receipt = questions.submit("request", question, "", "")
    assert receipt["state"] == "accepted"
    await asyncio.gather(*questions.tasks.values())
    done = questions.submit("request", question, "", "")
    assert done["after"] == receipt["after"] and done["before"] == receipt["before"]
    assert done["state"] == "completed" and done["window_count"] == 1
    assert [c["citation"] for c in done["citations"]] == ["captions/inside.json"]
    assert reviews == [question]
    assert "possible match" in done["summary"]
    await questions.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("verdict", ["matched", "uncertain", "not_matched"])
async def test_history_answer_keeps_reviewed_image_and_grounds_highlights(tmp_path, verdict):
    import base64
    from types import SimpleNamespace
    from cctv_operator.payloads.domain.window_evidence import display_frame

    store = CaptionStore(tmp_path / "camera.db", job_id="test", run_id="earlier-run", source_id="camera")
    account = save(store, "candidate", datetime.now(timezone.utc), "red")
    account["matched_via"] = "image"
    box = [300, 200, 700, 800]
    class VLM:
        async def review(self, model, question, *, jpeg, caption):
            assert jpeg == store.frame("candidate")
            return verdict, "The subject is partly obscured.", box
    questions = VideoQuestions(SimpleNamespace(store=store), VLM(), lambda: "test")
    answer = await questions._review("Was anyone wearing red?", {
        "observations": [account], "total": 1, "indexed": 1, "after": "", "before": ""})
    image = answer["image"]
    assert image["citation"] == answer["citations"][0]["citation"]
    assert image["run_id"] == "earlier-run"
    assert f"Review: {verdict.replace('_', ' ')}" in image["caption"]
    expected = display_frame(store.frame("candidate"), box if verdict == "matched" else None, thumbnail=True)
    assert base64.b64decode(image["data"]) == expected
    assert ("Box estimated" in image["caption"]) == (verdict == "matched")


@pytest.mark.asyncio
async def test_history_answer_prefers_matching_image_and_rejects_changed_bytes(tmp_path):
    from types import SimpleNamespace
    store = CaptionStore(tmp_path / "camera.db", job_id="test", run_id="run", source_id="camera")
    now = datetime.now(timezone.utc)
    rows = [{**save(store, str(i), now, color), "matched_via": "image"} for i, color in enumerate(["blue", "red"])]
    class VLM:
        async def review(self, model, question, *, jpeg, caption):
            return ("matched" if jpeg == coat("red") else "uncertain"), "Reviewed image.", None
    questions = VideoQuestions(SimpleNamespace(store=store), VLM(), lambda: "test")
    result = {"observations": rows, "total": 2, "indexed": 2, "after": "", "before": ""}
    assert (await questions._review("Red coat?", result))["image"]["citation"] == "captions/1.json"
    rows[0]["snapshot"]["sha256"] = "0" * 64
    with pytest.raises(ValueError, match="changed"):
        await questions._review("Red coat?", result)


@pytest.mark.skipif(not os.environ.get("CCTV_TEST_MEMBRANE_BINARY"), reason="Opt-in native Membrane and model gate")
def test_native_image_index_then_past_hour_recall(tmp_path, monkeypatch):
    root = (tmp_path / "membrane").resolve()
    root.mkdir()
    with socket.socket() as socket_:
        socket_.bind(("127.0.0.1", 0))
        address = "127.0.0.1:" + str(socket_.getsockname()[1])
    monkeypatch.setenv("MN_CONTEXT_ADDR", address)
    monkeypatch.setenv("MN_CONTEXT_FS_MEMORY_ROOT", str(root))
    monkeypatch.setenv("MN_CONTEXT_AUTH_TOKEN", "isolated-camera-test")
    service = subprocess.Popen([os.environ["CCTV_TEST_MEMBRANE_BINARY"]])
    try:
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)
        store = CaptionStore(tmp_path / "camera.db", job_id="test", run_id="first", source_id="camera")
        now = datetime.now(timezone.utc)
        save(store, "outside-hour", now - timedelta(minutes=62), "red")
        save(store, "red-coat", now - timedelta(minutes=45), "red")
        save(store, "blue-coat", now - timedelta(minutes=30), "blue")
        save(store, "green-coat", now - timedelta(minutes=20), "green")
        for minute in range(1, 14):
            save(store, f"recent-{minute}", now - timedelta(minutes=minute))
        history = VisualHistory(CONFIG, store)
        for _ in range(17):
            assert history.index_next()
        assert not history.index_next()
        assert store.index_counts(history.model) == (17, 17)
        service.terminate()
        service.wait(timeout=10)
        service = subprocess.Popen([os.environ["CCTV_TEST_MEMBRANE_BINARY"]])
        with grpc.insecure_channel(address) as channel:
            grpc.channel_ready_future(channel).result(timeout=10)
        next_run = CaptionStore(store.path, job_id="test", run_id="second", source_id="camera")
        next_history = VisualHistory(CONFIG, next_run, embeddings=history.embeddings)
        found = next_history.search(QUESTION, *search_interval(QUESTION, clock=now))
        assert found["total"] == found["indexed"] == 16
        assert found["observations"][0]["id"] == "red-coat"
        assert found["observations"][0]["matched_via"] == "image"
        assert all(item["id"] != "outside-hour" for item in found["observations"])
    finally:
        service.terminate()
        service.wait(timeout=10)
