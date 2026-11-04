"""Direct NVIDIA vss-rt-vlm 3.3 caption protocol, based on Spark's rt_vlm sample."""

import asyncio
from urllib.parse import quote

import httpx

from .errors import CameraStateError


async def sse_data(lines, *, max_bytes=1048576):
    """Parse bounded SSE records, including comments and multiline/final data."""
    data, size = [], 0
    async for line in lines:
        if not line:
            if data:
                yield "\n".join(data)
                data, size = [], 0
        elif line.startswith("data:"):
            value = line[5:]
            value = value[1:] if value.startswith(" ") else value
            size += len(value.encode()) + 1
            if size > max_bytes:
                raise ValueError("NVIDIA caption record exceeds its size limit.")
            data.append(value)
    if data:
        yield "\n".join(data)


class VLMClient:
    def __init__(self, base_url, client=None):
        self.base_url = base_url.rstrip("/")
        self.http = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/") + "/", trust_env=False,
            timeout=httpx.Timeout(15, read=120), follow_redirects=False,
        )

    async def model(self):
        response = await self.http.get("v1/ready", timeout=4)
        response.raise_for_status()
        response = await self.http.get("v1/models", timeout=5)
        response.raise_for_status()
        models = response.json().get("data", [])
        if not isinstance(models, list) or not models or not isinstance(models[0].get("id"), str):
            raise ValueError("NVIDIA has no loaded model.")
        return models[0]["id"]

    async def add_stream(self, settings):
        response = await self.http.post("v1/streams/add", timeout=20, json={
            "streams": [{"liveStreamUrl": settings.uri, "description": "OtterDesk CCTV co-worker"}],
        })
        response.raise_for_status()
        body = response.json()
        if body.get("errors") or not body.get("results"):
            raise ValueError("NVIDIA could not register the camera. Check its connection.")
        identity = body["results"][0].get("id")
        if not isinstance(identity, str) or not identity or len(identity) > 256:
            raise ValueError("NVIDIA returned an invalid stream identity.")
        return identity

    @staticmethod
    def caption_payload(stream_id, model, settings):
        return {
            "id": stream_id, "model": model, "prompt": settings.prompt, "stream": True,
            "chunk_duration": settings.chunk_duration, "chunk_overlap_duration": 0,
            "num_frames_per_second_or_fixed_frames_chunk": settings.frames_per_chunk,
            "use_fps_for_chunking": False, "vlm_input_width": 608, "vlm_input_height": 320,
            "max_tokens": settings.max_tokens, "temperature": 0.2,
            "enable_audio": False, "enable_reasoning": False,
        }

    async def cleanup(self, stream_id, request_id=None):
        path_id = quote(stream_id, safe="")
        response = await self.http.delete(
            f"v1/generate_captions/{path_id}",
            params={"request_id": request_id} if request_id else {}, timeout=10,
        )
        if response.status_code not in {200, 202, 204, 404}:
            response.raise_for_status()
        # NVIDIA can retain the resource briefly after caption cancellation.
        for attempt in range(5):
            response = await self.http.delete(f"v1/streams/delete/{path_id}", timeout=10)
            if response.status_code in {200, 202, 204, 404}:
                return
            if response.status_code != 409 or attempt == 4:
                response.raise_for_status()
            await asyncio.sleep(0.5 * (attempt + 1))


def safe_error(error):
    if isinstance(error, CameraStateError):
        return str(error)
    if isinstance(error, httpx.HTTPStatusError):
        return f"NVIDIA video analysis returned HTTP {error.response.status_code}. Check the VLM service."
    if isinstance(error, (httpx.TimeoutException, TimeoutError)):
        return "NVIDIA video analysis timed out. Check the camera and VLM service, then try again."
    if isinstance(error, httpx.TransportError):
        return "NVIDIA video analysis disconnected. Check the VLM service, then try again."
    # Upstream errors and decode errors can include stream URLs or response text.
    return "Couldn't analyze the video. Check the camera, VLM service and saved analysis status."
