"""Serve the CCTV operator page and claim its job-scoped iframe handle."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import mimetypes
import os
import signal
import secrets
import socket
import subprocess
import threading
import time
import urllib.parse
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Protocol

from mn_live_video_analysis_skill import redact_source_urls
from mn_sdk.blueprint_support import load_runtime_config
from mn_sdk_web_ui import claim_web_ui, mark_web_ui_status, resolve_web_ui_binding

SCRIPT_DIR = Path(__file__).resolve().parent
WEB_UI_NODE_ID = "cctv_web_ui"
WEB_UI_SERVICE_NAME = "cctv-operator-web-ui"
CCTV_MCP_PORT = 62009
CCTV_MCP_ENDPOINT_ARTIFACT = "cctv_operator_mcp_endpoint.json"
MJPEG_BOUNDARY = "cctv-frame"
MJPEG_CONTENT_TYPE = f"multipart/x-mixed-replace; boundary={MJPEG_BOUNDARY}"


class PreviewStream(Protocol):
    enabled: bool

    def frames(self) -> Iterator[bytes]: ...

    def snapshot(self) -> dict[str, str]: ...

    def stop(self) -> None: ...


class MJPEGPreviewSettings:
    def __init__(
        self,
        *,
        enabled: bool,
        source_uri: str,
        fps: float,
        width: int,
        jpeg_quality: int,
        reconnect_seconds: float,
    ) -> None:
        self.enabled = enabled
        self.source_uri = source_uri
        self.fps = fps
        self.width = width
        self.jpeg_quality = jpeg_quality
        self.reconnect_seconds = reconnect_seconds


def _bounded_number(
    value: Any,
    *,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    return min(max(parsed, minimum), maximum)


def mjpeg_preview_settings(config: Mapping[str, Any]) -> MJPEGPreviewSettings:
    web_ui = config.get("web_ui") if isinstance(config.get("web_ui"), Mapping) else {}
    preview = web_ui.get("preview") if isinstance(web_ui.get("preview"), Mapping) else {}
    video_source = (
        config.get("video_source")
        if isinstance(config.get("video_source"), Mapping)
        else {}
    )
    source_uri = str(
        os.environ.get("VIDEO_SOURCE_URI")
        or video_source.get("uri")
        or "rtsp://127.0.0.1:8554/cctv-demo"
    ).strip()
    scheme = urllib.parse.urlsplit(source_uri).scheme.lower()
    enabled = bool(preview.get("enabled", True)) and scheme in {
        "rtsp",
        "rtsps",
        "rtmp",
        "rtmps",
    }
    return MJPEGPreviewSettings(
        enabled=enabled,
        source_uri=source_uri,
        fps=_bounded_number(
            preview.get("fps"), default=8.0, minimum=1.0, maximum=15.0
        ),
        width=int(
            _bounded_number(
                preview.get("width"), default=1280, minimum=320, maximum=1920
            )
        ),
        jpeg_quality=int(
            _bounded_number(
                preview.get("jpeg_quality"), default=5, minimum=2, maximum=20
            )
        ),
        reconnect_seconds=_bounded_number(
            preview.get("reconnect_seconds"),
            default=1.0,
            minimum=0.25,
            maximum=10.0,
        ),
    )


def ffmpeg_mjpeg_command(settings: MJPEGPreviewSettings) -> list[str]:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-nostdin",
        "-fflags",
        "nobuffer",
        "-flags",
        "low_delay",
    ]
    if urllib.parse.urlsplit(settings.source_uri).scheme.lower() in {"rtsp", "rtsps"}:
        command.extend(["-rtsp_transport", "tcp"])
    command.extend(
        [
            "-hwaccel",
            "cuda",
            "-hwaccel_output_format",
            "cuda",
            "-i",
            settings.source_uri,
            "-an",
            "-vf",
            (
                f"scale_cuda=w={settings.width}:h=-2:format=nv12,"
                f"hwdownload,format=nv12,fps={settings.fps:g}"
            ),
            "-c:v",
            "mjpeg",
            "-q:v",
            str(settings.jpeg_quality),
            "-f",
            "image2pipe",
            "pipe:1",
        ]
    )
    return command


class CUDAMJPEGPreview:
    """Relay one GPU-decoded source to any number of MJPEG clients."""

    def __init__(self, settings: MJPEGPreviewSettings) -> None:
        self.settings = settings
        self.enabled = settings.enabled
        self._condition = threading.Condition()
        self._latest_frame = b""
        self._revision = 0
        self._status = "starting" if self.enabled else "disabled"
        self._warning = ""
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._process: subprocess.Popen[bytes] | None = None

    def ensure_started(self) -> None:
        if not self.enabled or self._stop_event.is_set():
            return
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                return
            self._thread = threading.Thread(
                target=self._run,
                name="cctv-mjpeg-preview",
                daemon=True,
            )
            self._thread.start()

    def frames(self) -> Iterator[bytes]:
        self.ensure_started()
        revision = -1
        while not self._stop_event.is_set():
            with self._condition:
                self._condition.wait_for(
                    lambda current_revision=revision: self._revision != current_revision
                    or self._stop_event.is_set(),
                    timeout=10.0,
                )
                if self._stop_event.is_set():
                    return
                if not self._latest_frame:
                    revision = self._revision
                    continue
                if self._revision == revision:
                    continue
                revision = self._revision
                frame = self._latest_frame
            yield frame

    def snapshot(self) -> dict[str, str]:
        with self._condition:
            return {"status": self._status, "warning": self._warning}

    def stop(self) -> None:
        self._stop_event.set()
        with self._condition:
            process = self._process
            self._condition.notify_all()
        if process is not None and process.poll() is None:
            process.terminate()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=3)

    def _set_status(self, status: str, warning: str = "") -> None:
        with self._condition:
            self._status = status
            self._warning = warning
            self._condition.notify_all()

    def _publish(self, frame: bytes) -> None:
        with self._condition:
            self._latest_frame = frame
            self._revision += 1
            self._status = "live"
            self._warning = ""
            self._condition.notify_all()

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._set_status("connecting" if not self._latest_frame else "reconnecting")
            try:
                process = subprocess.Popen(
                    ffmpeg_mjpeg_command(self.settings),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    bufsize=0,
                )
            except OSError:
                self._set_status(
                    "unavailable",
                    "The CUDA preview relay could not start in the media worker.",
                )
                self._stop_event.wait(self.settings.reconnect_seconds)
                continue
            with self._condition:
                self._process = process
            try:
                if process.stdout is not None:
                    self._read_frames(process.stdout)
            finally:
                if process.poll() is None:
                    process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
                with self._condition:
                    if self._process is process:
                        self._process = None
            if not self._stop_event.is_set():
                self._set_status(
                    "reconnecting",
                    "The source preview is reconnecting; analysis remains independent.",
                )
                self._stop_event.wait(self.settings.reconnect_seconds)

    def _read_frames(self, stream: Any) -> None:
        buffer = bytearray()
        max_buffer_bytes = 16 * 1024 * 1024
        while not self._stop_event.is_set():
            chunk = stream.read(64 * 1024)
            if not chunk:
                return
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start < 0:
                    if len(buffer) > 1:
                        del buffer[:-1]
                    break
                end = buffer.find(b"\xff\xd9", start + 2)
                if end < 0:
                    if start:
                        del buffer[:start]
                    if len(buffer) > max_buffer_bytes:
                        buffer.clear()
                    break
                frame_end = end + 2
                self._publish(bytes(buffer[start:frame_end]))
                del buffer[:frame_end]


def _load_domain_function(module_name: str, function_name: str) -> Callable:
    for ancestor in (SCRIPT_DIR, *SCRIPT_DIR.parents):
        module_path = ancestor / "domain" / f"{module_name}.py"
        if not module_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location(f"cctv_operator_{module_name}", module_path)
        if spec is None or spec.loader is None:
            break
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, function_name)
    raise RuntimeError(f"cctv_operator {module_name} is unavailable")


operator_state = _load_domain_function("dashboard", "operator_state")
_dashboard_html = _load_domain_function("media", "dashboard_html")


def load_config() -> dict[str, Any]:
    return load_runtime_config(__file__)


def configured_run_id() -> str:
    return str(os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run").strip()


def configured_run_dir() -> Path:
    explicit = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser()
    root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    return Path(root).expanduser() / configured_run_id() if root else Path.cwd() / "runs" / configured_run_id()


def configured_job_data_dir(job_id: str) -> Path:
    value = str(os.environ.get("MN_JOB_DATA_DIR") or "").strip()
    if not value:
        raise RuntimeError("CCTV Web UI requires the job-scoped MN_JOB_DATA_DIR contract")
    directory = Path(value).expanduser().resolve()
    if directory.name != job_id:
        raise RuntimeError("MN_JOB_DATA_DIR must identify the direct directory for MN_JOB_ID")
    return directory


class CCTVWebUIService:
    def __init__(
        self,
        *,
        run_id: str,
        run_dir: Path,
        config: dict[str, Any],
        preview_stream: PreviewStream | None = None,
    ) -> None:
        self.run_id = run_id
        self.run_dir = run_dir
        self.config = config
        self.preview_stream = preview_stream or CUDAMJPEGPreview(
            mjpeg_preview_settings(config)
        )
        self._stop_event = threading.Event()
        self._activity_store = None

    def attach_activity_store(self, store: Any) -> None:
        self._activity_store = store

    def sync_mcp_activity(self, state: Mapping[str, Any] | None = None) -> list[dict[str, Any]]:
        if self._activity_store is None:
            return []
        projected = dict(state or self.ui_state())
        events = projected.get("events") if isinstance(projected.get("events"), list) else []
        published = []
        for event in reversed(events):
            if not isinstance(event, Mapping):
                continue
            title = " ".join(str(event.get("type") or "Activity observed").split())[:240]
            message = " ".join(str(event.get("summary") or "").split())[:8_000]
            occurred_at = " ".join(str(event.get("timestamp") or "").split())[:80]
            if not message:
                continue
            digest = hashlib.sha256(
                f"{self.run_id}\0{title}\0{occurred_at}\0{message}".encode()
            ).hexdigest()[:32]
            activity = {
                "schema_version": "mn.mcp.job_activity.v1",
                "event_id": digest,
                "title": title,
                "message": message,
                "occurred_at": occurred_at,
                "source": "cctv_operator",
                "requires_review": title in {"Operator notice", "Target observed"},
                **({"details": event["details"]} if event.get("details") else {}),
            }
            published.append(
                self._activity_store.publish_result(
                    digest,
                    activity,
                    stage="live_activity",
                    summary=f"{title}: {message}"[:2_000],
                    idempotency_key=f"cctv-activity:{digest}",
                )
            )
        return published

    def ui_state(self) -> dict[str, Any]:
        events = read_event_tail(self.run_dir / "events.jsonl", limit=80)
        attention = _event_payload(_latest_event(events, "cctv_operator_attention_updated"))
        durable = read_monitoring_state(self.run_dir / "monitoring_state.json")
        if int(durable.get("instruction_revision") or 0) >= int(attention.get("instruction_revision") or 0):
            attention = durable
        report = read_json_object(self.run_dir / "cctv_report.json")
        batch = _event_payload(_latest_event(events, "cctv_operator_frame_batch_ready"))
        if batch and not isinstance(report.get("latest_batch"), dict):
            report = {**report, "latest_batch": batch}
        preview = self.preview_stream.snapshot()
        state = operator_state(
            run_id=self.run_id,
            config=self.config,
            report=report,
            latest_frame=read_json_object(self.run_dir / "latest_analyzed_frame.json"),
            monitoring=attention,
            supplemental_events=events,
            preview_status=str(preview.get("status") or "unavailable"),
            preview_warning=str(preview.get("warning") or ""),
        )
        safe_state = json.loads(redact_source_urls(json.dumps(state)))
        if self._activity_store is not None:
            self.sync_mcp_activity(safe_state)
        return safe_state

    def state_events(self) -> Iterator[tuple[int, dict[str, Any]]]:
        sequence = 0
        previous = ""
        last_keepalive = time.monotonic()
        while not self._stop_event.is_set():
            state = self.ui_state()
            encoded = json.dumps(state, separators=(",", ":"), sort_keys=True)
            now = time.monotonic()
            if encoded != previous:
                sequence += 1
                previous = encoded
                last_keepalive = now
                yield sequence, state
            elif now - last_keepalive >= 15:
                last_keepalive = now
                yield sequence, {}
            self._stop_event.wait(0.75)

    def stop(self) -> None:
        self._stop_event.set()
        self.preview_stream.stop()


class CCTVWebUIServer:
    def __init__(self, service: CCTVWebUIService, *, host: str, port: int) -> None:
        self.service = service
        self._server = ThreadingHTTPServer((host, port), _handler_for(service))

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._server.serve_forever(poll_interval=0.5)

    def stop(self) -> None:
        self.service.stop()
        self._server.shutdown()
        self._server.server_close()


def _handler_for(service: CCTVWebUIService) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            path = urllib.parse.urlsplit(self.path).path
            if path == "/":
                self._send(_dashboard_html().encode(), "text/html; charset=utf-8")
                return
            if path == "/health":
                self._json({"status": "ok", "component": "cctv-web-ui"})
                return
            if path == "/ui/state":
                self._json(service.ui_state())
                return
            if path == "/streams/live.mjpg":
                self._mjpeg()
                return
            if path == "/streams/operator-events":
                self._operator_events()
                return
            if path.startswith("/artifacts/"):
                self._artifact(path.removeprefix("/artifacts/"))
                return
            self._json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            self._json({"error": "not found"}, status=404)

        def _artifact(self, name: str) -> None:
            if name not in {
                "latest_analyzed_frame.jpg",
                "latest_analyzed_frame.json",
            }:
                self._json({"error": "not found"}, status=404)
                return
            path = service.run_dir / name
            try:
                body = path.read_bytes()
            except OSError:
                self._json({"error": "artifact not found"}, status=404)
                return
            self._send(body, mimetypes.guess_type(name)[0] or "application/octet-stream")

        def _mjpeg(self) -> None:
            if not service.preview_stream.enabled:
                self._json({"error": "live preview is disabled"}, status=503)
                return
            self.send_response(200)
            self.send_header("Content-Type", MJPEG_CONTENT_TYPE)
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Pragma", "no-cache")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                for frame in service.preview_stream.frames():
                    self.wfile.write(f"--{MJPEG_BOUNDARY}\r\n".encode())
                    self.wfile.write(b"Content-Type: image/jpeg\r\n")
                    self.wfile.write(f"Content-Length: {len(frame)}\r\n\r\n".encode())
                    self.wfile.write(frame)
                    self.wfile.write(b"\r\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def _operator_events(self) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
            self.send_header("Connection", "close")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            try:
                for sequence, state in service.state_events():
                    if state:
                        body = json.dumps(state, separators=(",", ":"))
                        self.wfile.write(f"id: {sequence}\n".encode())
                        self.wfile.write(b"event: operator-state\n")
                        self.wfile.write(f"data: {body}\n\n".encode())
                    else:
                        self.wfile.write(b": keep-alive\n\n")
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                return

        def _json(self, value: dict[str, Any], *, status: int = 200, headers: dict[str, str] | None = None) -> None:
            self._send(json.dumps(value, separators=(",", ":")).encode(), "application/json; charset=utf-8", status=status, headers=headers)

        def _send(self, body: bytes, content_type: str, *, status: int = 200, headers: dict[str, str] | None = None) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return Handler


def read_event_tail(path: Path, *, limit: int) -> list[dict[str, Any]]:
    if not path.is_file() or limit < 1:
        return []
    rows: deque[dict[str, Any]] = deque(maxlen=limit)
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            value = json.loads(line)
            if isinstance(value, dict):
                rows.append(json.loads(redact_source_urls(json.dumps(value))))
    except (OSError, json.JSONDecodeError):
        return list(rows)
    return list(rows)


def read_monitoring_state(path: Path) -> dict[str, Any]:
    value = read_json_object(path)
    if not isinstance(value.get("instruction"), str):
        return {}
    try:
        revision = max(int(value.get("instruction_revision") or 0), 0)
    except (TypeError, ValueError):
        return {}
    return {
        "instruction": " ".join(value["instruction"].split())[:500],
        "instruction_revision": revision,
        "updated_at": value.get("updated_at"),
        "command_id": str(value.get("last_command_id") or "")[:500],
    }


def read_json_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def _latest_event(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    return next((event for event in reversed(events) if event.get("type") == event_type), {})


def _event_payload(event: dict[str, Any]) -> dict[str, Any]:
    value = event.get("payload")
    return value if isinstance(value, dict) else {}


def public_service_url(host: str, port: int) -> str:
    explicit = str(os.environ.get("MN_BLUEPRINT_WEB_UI_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    node = str(os.environ.get("MN_EXECUTION_NODE") or "").strip()
    if host in {"0.0.0.0", "::", "[::]"} and "@" in node:
        return f"http://{node.rpartition('@')[2]}:{port}"
    proxy_host = str(os.environ.get("MN_WEB_UI_PROXY_HOST") or os.environ.get("MN_DOCKER_WORKER_CONTAINER_NAME") or "").strip()
    if proxy_host:
        return f"http://{proxy_host}:{port}"
    if host in {"0.0.0.0", "::", "[::]"}:
        return f"http://127.0.0.1:{port}"
    return f"http://{host}:{port}"


def create_operator_mcp_server(
    service: CCTVWebUIService,
    *,
    job_id: str,
    run_id: str,
    run_dir: Path,
    host: str = "127.0.0.1",
    port: int = CCTV_MCP_PORT,
    server_factory: Callable[..., Any] | None = None,
    runtime_service: Any | None = None,
):
    """Create CCTV's own job agent MCP using the shared SDK MRTR package."""

    from mcp.server.mcpserver import Context
    from mcp.types import InputRequiredResult
    from mn_sdk.blueprint_support import acknowledge_human_notice
    from mn_sdk_mcp import (
        JobExchangeStore,
        create_mrtr_mcp_server,
        job_activity_input_required,
        resolve_job_activity_receipt,
    )
    # MCP evaluates postponed annotations against module globals when tools are
    # registered. Keep imports lazy for blueprint inspection environments while
    # making the exact MRTR control-flow types available to that evaluator.
    globals()["Context"] = Context
    globals()["InputRequiredResult"] = InputRequiredResult

    store = JobExchangeStore(
        run_dir / "cctv_operator_mcp.sqlite3",
        allowed_root=run_dir,
        job_id=job_id,
        blueprint_id="cctv_operator",
        run_id=run_id,
    )
    service.attach_activity_store(store)
    server = create_mrtr_mcp_server(
        "CCTV Operator agent",
        instructions=(
            "Inspect the current operator status and activity before answering. "
            "Use set_monitoring_instruction to change what the current run analyzes. "
            "Use watch_operator_activity for a bounded live wait. A transport receipt "
            "does not acknowledge an operator notice."
        ),
        host=host,
        port=port,
        server_factory=server_factory,
    )

    @server.tool(name="get_operator_status", structured_output=True)
    def get_operator_status() -> dict[str, Any]:
        state = service.ui_state()
        metrics = state["metrics"]
        finding = metrics["latest finding"]
        observed_at = metrics["last analyzed"]
        return {
            "schema_version": "mn.cctv.operator_status.v1",
            "ready": True,  # Control availability does not depend on a first detection.
            "status": metrics["status"],
            "finding": finding,
            "observed_at": observed_at,
            "summary": f"{finding} Last analyzed: {observed_at}.",
            "metrics": metrics,
            "details": state.get("finding_details", []),
            "warning": state.get("warning"),
        }

    @server.tool(name="get_operator_activity", structured_output=True)
    def get_operator_activity(after_revision: str = "0") -> dict[str, Any]:
        service.ui_state()
        try:
            cursor = max(int(after_revision or 0), 0)
        except (TypeError, ValueError) as error:
            raise ValueError("after_revision must be a non-negative integer string") from error
        return store.updates(after_revision=cursor, kinds=["result"], limit=100)

    @server.tool(name="watch_operator_activity", structured_output=True)
    async def watch_operator_activity(
        after_event_id: str = "",
        wait_seconds: str = "20",
        ctx: Context = None,
    ) -> dict[str, Any] | InputRequiredResult:
        if ctx is not None:
            receipt = resolve_job_activity_receipt(ctx)
            if receipt is not None:
                return receipt
        try:
            wait = min(max(float(wait_seconds or 0), 0.0), 25.0)
        except (TypeError, ValueError) as error:
            raise ValueError("wait_seconds must be numeric") from error
        deadline = time.monotonic() + wait
        cursor = str(after_event_id or "")[:256]
        while True:
            service.ui_state()
            updates = store.updates(after_revision=0, kinds=["result"], limit=200)["updates"]
            activities = [
                item.get("payload")
                for item in updates
                if isinstance(item.get("payload"), Mapping)
            ]
            activity = None
            if not cursor and activities:
                activity = activities[-1]
            elif cursor:
                for index, candidate in enumerate(activities):
                    if candidate.get("event_id") == cursor:
                        activity = activities[index + 1] if index + 1 < len(activities) else None
                        break
                if activity is None and activities and activities[-1].get("event_id") != cursor:
                    activity = activities[-1]
            if activity is not None:
                return job_activity_input_required(activity, after_event_id=cursor)
            if time.monotonic() >= deadline:
                return {
                    "schema_version": "mn.mcp.job_activity_watch.v1",
                    "delivered": False,
                    "cursor": cursor,
                    "activity": None,
                }
            await __import__("asyncio").sleep(min(0.5, max(0.0, deadline - time.monotonic())))

    @server.tool(name="acknowledge_operator_notice", structured_output=True)
    def acknowledge_operator_notice(command_id: str, notice_id: str) -> dict[str, Any]:
        resolved_command_id = str(command_id or "").strip()[:128]
        resolved_notice_id = str(notice_id or "").strip()[:256]
        if not resolved_command_id or not resolved_notice_id:
            raise ValueError("command_id and notice_id are required")
        acknowledge_human_notice(
            run_id,
            resolved_notice_id,
            {"reviewer": "cctv_operator_mcp"},
            runs_root=run_dir.parent,
        )
        return store.publish_status(
            "completed",
            stage="acknowledge_operator_notice",
            summary="Operator notice acknowledged.",
            metadata={"notice_id": resolved_notice_id},
            publication_state="final",
            idempotency_key=f"cctv-command:{resolved_command_id}",
            record_id=resolved_command_id,
        )["payload"] | {
            "schema_version": "mn.cctv.command_receipt.v1",
            "command_id": resolved_command_id,
            "notice_id": resolved_notice_id,
            "state": "completed",
        }

    @server.tool(name="set_monitoring_instruction", structured_output=True)
    def set_monitoring_instruction(
        command_id: str,
        instruction: str = "",
        clear: Literal["true", "false"] = "false",
        analyze_now: Literal["true", "false"] = "true",
    ) -> dict[str, Any]:
        resolved_command_id = str(command_id or "").strip()
        resolved_instruction = " ".join(str(instruction or "").split())[:500]
        resolved_clear = str(clear or "false").strip().lower()
        resolved_analyze_now = str(analyze_now or "true").strip().lower()
        if resolved_clear not in {"true", "false"} or resolved_analyze_now not in {
            "true",
            "false",
        }:
            raise ValueError("clear and analyze_now must be true or false")
        clear_enabled = resolved_clear == "true"
        analyze_now_enabled = resolved_analyze_now == "true"
        if not resolved_command_id:
            raise ValueError("command_id is required")
        if not clear_enabled and not resolved_instruction:
            raise ValueError("instruction is required unless clear=true")
        sender = runtime_service
        if sender is None:
            from mn_sdk import RuntimeConfig, RuntimeService, build_runtime_client

            sender = RuntimeService(build_runtime_client(RuntimeConfig.from_env()))
        accepted = sender.send_run_input(
            run_id,
            "steer_monitoring",
            {
                "command_id": resolved_command_id,
                "instruction": resolved_instruction,
                "clear": clear_enabled,
                "analyze_now": analyze_now_enabled,
            },
            idempotency_key=resolved_command_id,
        )
        store.publish_status(
            "accepted",
            stage="set_monitoring_instruction",
            summary=(
                "Monitoring instruction clear was accepted."
                if clear_enabled
                else f"Monitoring instruction was accepted: {resolved_instruction}"
            ),
            metadata={
                "instruction": resolved_instruction,
                "clear": clear_enabled,
                "analyze_now": analyze_now_enabled,
            },
            publication_state="final",
            idempotency_key=f"cctv-command:{resolved_command_id}",
            record_id=resolved_command_id,
        )
        return {
            "schema_version": "mn.cctv.command_receipt.v1",
            "command_id": resolved_command_id,
            "state": str(accepted.get("status") or "accepted"),
            "input_id": "steer_monitoring",
        }

    @server.tool(name="get_command_status", structured_output=True)
    def get_command_status(command_id: str) -> dict[str, Any]:
        resolved_command_id = str(command_id or "").strip()[:128]
        record = store.get_record("status", resolved_command_id, include_staged=True)
        monitoring = read_monitoring_state(run_dir / "monitoring_state.json")
        state = str((record or {}).get("payload", {}).get("status") or "unknown")
        if monitoring.get("command_id") == resolved_command_id:
            state = "completed"
        return {
            "schema_version": "mn.cctv.command_receipt.v1",
            "command_id": resolved_command_id,
            "state": state,
            "instruction": monitoring.get("instruction") if state == "completed" else None,
            "instruction_revision": (
                monitoring.get("instruction_revision") if state == "completed" else None
            ),
            "record": record,
        }

    return server


def _open_listener(host: str, port: int = 0) -> tuple[socket.socket, int]:
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((host, port))
        listener.listen(socket.SOMAXCONN)
    except Exception:
        listener.close()
        raise
    return listener, int(listener.getsockname()[1])


def _run_operator_mcp(server: Any, listener: socket.socket) -> None:
    import uvicorn

    options = dict(getattr(server, "_mn_http_options", {}))
    options.pop("port", None)
    app = server.streamable_http_app(**options)
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="info")).run(sockets=[listener])
    finally:
        listener.close()


def start_operator_mcp_server(
    service: CCTVWebUIService,
    *,
    job_id: str,
    run_id: str,
    run_dir: Path,
) -> tuple[threading.Thread, int]:
    """Start the SDK MRTR server on a private, OS-selected owner-node port."""

    from cctv_operator_mcp import create_mcp_proxy

    listener, port = _open_listener("127.0.0.1")
    try:
        server = create_operator_mcp_server(
            service,
            job_id=job_id,
            run_id=run_id,
            run_dir=run_dir,
            host="127.0.0.1",
            port=port,
        )
        # Core's HostLocal sidecar is in a different network namespace. Only
        # this authenticated relay crosses that boundary; MCP stays loopback.
        token = secrets.token_urlsafe(32)
        proxy = create_mcp_proxy(
            {"url": f"http://127.0.0.1:{port}"}, port=0, access_token=token
        )
    except Exception:
        listener.close()
        raise
    thread = threading.Thread(
        target=_run_operator_mcp,
        args=(server, listener),
        name="cctv-operator-private-mcp",
        daemon=True,
    )
    thread.start()
    threading.Thread(
        target=proxy.serve_forever, name="cctv-operator-mcp-relay", daemon=True
    ).start()
    relay_port = int(proxy.server_address[1])
    endpoint = {
        "schema_version": "mn.cctv.operator_mcp_endpoint.v1",
        "url": f"http://host.docker.internal:{relay_port}",
        "port": relay_port,
        "token": token,
        "run_id": run_id,
    }
    target = run_dir / CCTV_MCP_ENDPOINT_ARTIFACT
    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    with temporary.open("x", encoding="utf-8") as handle:
        os.chmod(temporary, 0o600)
        handle.write(json.dumps(endpoint, sort_keys=True) + "\n")
    os.replace(temporary, target)
    return thread, port


def main() -> int:
    config = load_config()
    run_id = configured_run_id()
    job_id = str(os.environ.get("MN_JOB_ID") or run_id).strip()
    run_dir = configured_run_dir()
    job_data_dir = configured_job_data_dir(job_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    binding = resolve_web_ui_binding(config)
    service = CCTVWebUIService(run_id=run_id, run_dir=run_dir, config=config)
    mcp_thread, _mcp_port = start_operator_mcp_server(
        service,
        job_id=job_id,
        run_id=run_id,
        run_dir=run_dir,
    )
    if not mcp_thread.is_alive():
        raise RuntimeError("CCTV Operator MCP failed to start")
    server = CCTVWebUIServer(service, host=binding.host, port=binding.port)
    _bound_host, port = server.address
    claim_web_ui(
        job_data_dir,
        job_id=job_id,
        title="CCTV Operator",
        url=public_service_url(binding.host, port),
        service_name=WEB_UI_SERVICE_NAME,
        node_id=WEB_UI_NODE_ID,
        http_ports=[port],
        metadata={"run_id": run_id, "upstream": "cctv-operator-docker-worker"},
    )

    def stop(_signum: int, _frame: Any) -> None:
        mark_web_ui_status(job_data_dir, job_id=job_id, status="stopped", detail="The CCTV service is paused or cancelled.")
        threading.Thread(target=server.stop, daemon=True).start()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    server.serve_forever()
    return 0




if __name__ == "__main__":
    raise SystemExit(main())
