"""One owned NVIDIA request, durable captions and serial monitoring changes."""

import asyncio
import hashlib
import json
import math
import uuid

import httpx

from .caption_store import now, timestamp
from .errors import CameraStateError
from .realtime_client import safe_error, sse_data


class Analysis:
    def __init__(self, client, settings, store, publish, save_status):
        self.client, self.settings, self.store = client, settings, store
        self.configured_prompt = settings.prompt
        self.publish, self.save_status = publish, save_status
        self.task = None
        self.lock = asyncio.Lock()
        self.seen = set()
        self.revision = 0
        self.closing = False
        self.state = {"status": "ready", "total_captions": 0, "error": None,
                      "camera": settings.name, "instruction": settings.prompt, "instruction_revision": 0}

    def snapshot(self):
        result = self.store.history(current_run=True)
        return {"session": dict(self.state), "captions": result["observations"],
                "omitted_count": result["omitted_count"]}

    def update(self, **values):
        self.state.update(values)
        self.save_status(dict(self.state))

    async def start(self):
        async with self.lock:
            await self._start()

    async def _start(self):
        if self.closing:
            raise CameraStateError("Camera analysis is stopping. Start it again through OtterDesk when ready.")
        if self.task and not self.task.done():
            raise ValueError("Camera analysis is already running.")
        lease = self.store.state("active_request")
        if lease:
            if not lease.get("stream_id"):
                raise ValueError("A previous camera registration has an unknown outcome. Reconcile it in NVIDIA before starting again.")
            if lease.get("origin") != self.client.base_url:
                raise ValueError("The outstanding camera request belongs to another NVIDIA service. Reconcile it before changing the endpoint.")
            await self.client.cleanup(lease["stream_id"], lease.get("request_id"))
            self.store.set_state("active_request", None)
        model = await self.client.model()
        saved_goal = self.store.state("goal:" + self.store.run_id)
        if saved_goal:
            self.settings = self.settings.model_copy(update={"prompt": saved_goal["instruction"]})
            self.revision = saved_goal["revision"]
        self.seen.clear()
        self.session_id = uuid.uuid4().hex
        self.update(status="starting", model=model, started_at=now(), error=None,
                    instruction=self.settings.prompt, instruction_revision=self.revision,
                    total_captions=self.store.history(current_run=True)["total_count"])
        for caption in self.store.pending():
            self.publish(caption)
            self.store.published(caption["id"])
        self.task = asyncio.create_task(self._run(model))

    async def stop(self):
        async with self.lock:
            await self._stop()

    async def close(self):
        self.closing = True
        await self.stop()

    async def _stop(self):
        if self.task and not self.task.done():
            self.update(status="stopping")
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                # A stop before _run's first instruction cannot own a stream.
                self.update(status="stopped", stopped_at=now())
        if self.store.state("active_request"):
            raise RuntimeError("The NVIDIA camera request was not fully released. Check analysis status before retrying.")

    async def change_goal(self, identity, instruction, clear=False):
        if not isinstance(identity, str) or not identity.strip() or len(identity) > 128:
            raise ValueError("A request ID of 1–128 characters is required.")
        if not isinstance(instruction, str) or len(instruction) > 4000 or (not clear and not instruction.strip()):
            raise ValueError("Enter a visible condition to monitor.")
        request = {"run_id": self.store.run_id, "instruction": instruction, "clear": clear}
        async with self.lock:
            previous = self.store.command(identity, request)
            if previous:
                return previous
            from .settings import DEFAULT_PROMPT
            selected = self.configured_prompt if clear else instruction.strip()
            # Retain the accepted intent and one revision across interrupted replies.
            saved = self.store.state("goal:" + self.store.run_id)
            revision = (saved or {}).get("revision", self.revision) + 1
            receipt = {"state": "accepted", "accepted": True, "command_id": identity,
                       "operation_id": identity, "instruction_revision": revision,
                       "summary": "Monitoring change accepted; waiting for the previous request to stop."}
            self.store.command(identity, request, receipt)
            try:
                await self._stop()
                self.store.set_state("goal:" + self.store.run_id,
                                     {"instruction": selected or DEFAULT_PROMPT, "revision": revision})
                await self._start()
                receipt.update(state="completed", instruction=selected, analysis_ready=False,
                               summary="Monitoring goal applied. The next completed video window will use it.")
            except Exception as error:
                receipt.update(state="failed", summary=safe_error(error))
            self.store.command(identity, request, receipt)
            return receipt

    async def _run(self, model):
        stream_id = None
        try:
            # A process crash before the response is known must not blindly add again.
            self.store.set_state("active_request", {"registration_pending": True, "session_id": self.session_id,
                                                    "origin": self.client.base_url})
            registration = asyncio.create_task(self.client.add_stream(self.settings))
            try:
                stream_id = await asyncio.shield(registration)
            except asyncio.CancelledError:
                # Registration may have reached NVIDIA. Recover its ID before cleanup.
                stream_id = await registration
                raise
            finally:
                if stream_id:
                    self.store.set_state("active_request", {"stream_id": stream_id, "request_id": None,
                                                            "origin": self.client.base_url})
            payload = self.client.caption_payload(stream_id, model, self.settings)
            async with self.client.http.stream(
                "POST", "v1/generate_captions", json=payload,
                timeout=httpx.Timeout(15, read=self.settings.caption_timeout_seconds),
            ) as response:
                response.raise_for_status()
                self._request_id(stream_id, response.headers.get("x-request-id"))
                self.update(status="running")
                records = sse_data(response.aiter_lines())
                while True:
                    try:
                        data = await asyncio.wait_for(anext(records), self.settings.caption_timeout_seconds)
                    except StopAsyncIteration:
                        raise ValueError("The live caption stream ended unexpectedly.") from None
                    if data.strip() == "[DONE]":
                        raise ValueError("The live caption stream ended unexpectedly.")
                    result = json.loads(data)
                    if not isinstance(result, dict) or result.get("error"):
                        raise ValueError("NVIDIA reported an inference error.")
                    if result.get("request_id"):
                        self._request_id(stream_id, result["request_id"])
                    chunks = result.get("chunk_responses", [])
                    if not isinstance(chunks, list) or len(chunks) > 64:
                        raise ValueError("Unexpected NVIDIA caption response.")
                    for chunk in chunks:
                        self.caption(chunk)
        except asyncio.CancelledError:
            pass
        except Exception as error:
            self.update(status="error", error=safe_error(error))
        finally:
            if stream_id:
                try:
                    lease = self.store.state("active_request") or {}
                    await self.client.cleanup(stream_id, lease.get("request_id"))
                    self.store.set_state("active_request", None)
                except Exception:
                    self.update(status="error", error="Couldn't release the NVIDIA camera request. Check the VLM service before starting again.")
            self.update(status="error" if self.state["status"] == "error" else "stopped", stopped_at=now())

    def _request_id(self, stream_id, request_id):
        if request_id is not None and (not isinstance(request_id, str) or not request_id or len(request_id) > 256):
            raise ValueError("Invalid NVIDIA request identity.")
        lease = self.store.state("active_request") or {}
        self.store.set_state("active_request", {"stream_id": stream_id, "request_id": request_id or lease.get("request_id"),
                                                "origin": self.client.base_url})

    def caption(self, chunk):
        if not isinstance(chunk, dict) or not isinstance(chunk.get("content"), str):
            raise ValueError("Unexpected NVIDIA caption content.")
        content = chunk["content"].strip()
        if not content:
            return
        if len(content) > 8192 or "<think>" in content.lower() or chunk.get("finish_reason") not in {None, "stop"}:
            raise ValueError("Incomplete or private NVIDIA caption content.")
        start, end = timestamp(chunk.get("start_time")), timestamp(chunk.get("end_time"))
        if start > end:
            raise ValueError("Caption times are out of order.")
        key = hashlib.sha256(json.dumps([chunk.get("chunk_id"), start, end], sort_keys=True).encode()).hexdigest()
        if key in self.seen:
            return
        latencies = {}
        for field in ("vlm_latency_ms", "chunk_latency_ms"):
            value = chunk.get(field)
            if value is not None and (isinstance(value, bool) or not isinstance(value, (int, float))
                                      or not math.isfinite(value) or value < 0):
                raise ValueError("Invalid NVIDIA timing.")
            latencies[field] = value
        caption = {"id": self.session_id + ":" + key, "run_id": self.store.run_id,
                   "camera": self.settings.name, "source_id": self.settings.source_id,
                   "content": content, "summary": content, "scene_understanding": content,
                   "start_time": start, "end_time": end, "received_at": now(),
                   "instruction": self.settings.prompt, "instruction_revision": self.revision,
                   "model": self.state["model"], "evidence_kind": "nvidia_video_window_caption",
                   "source_refs": ["captions/" + self.session_id + "-" + key + ".json"],
                   **latencies}
        if not self.store.append(caption):
            caption = self.store.saved(caption["id"])
        # Publication follows the durable source, never acceptance of an SSE packet.
        self.publish(caption)
        self.store.published(caption["id"])
        self.seen.add(key)
        if len(self.seen) > 600:
            self.seen = {key}
        self.update(total_captions=self.store.history(current_run=True)["total_count"],
                    last_caption_at=caption["received_at"], inference_ms=caption["vlm_latency_ms"])
