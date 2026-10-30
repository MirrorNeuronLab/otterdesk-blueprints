"""Serve the CCTV operator page and claim its job-scoped iframe handle."""

from __future__ import annotations

import hashlib
import importlib.util
import importlib
import json
import mimetypes
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
import urllib.parse
from collections import deque
from collections.abc import Callable, Iterator, Mapping
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Literal, Protocol

from mn_live_video_analysis_skill import redact_source_urls
from mn_sdk_common.files import atomic_write_json

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

    def latest_frame(self) -> tuple[int, float, bytes]: ...

    def ensure_started(self) -> None: ...

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
    # Preview visibility is a presentation control. The resident camera owner
    # still feeds detection and captions when the browser preview is hidden.
    enabled = scheme in {
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
                f"fps={settings.fps:g},scale_cuda=w={settings.width}:h=-2:format=nv12,"
                "hwdownload,format=nv12"
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
        self._published_at = 0.0
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

    def latest_frame(self) -> tuple[int, float, bytes]:
        with self._condition:
            return self._revision, self._published_at, self._latest_frame

    def wait_for_first_frame(self, timeout_seconds: float = 30.0) -> bool:
        self.ensure_started()
        with self._condition:
            return self._condition.wait_for(
                lambda: bool(self._latest_frame) or self._stop_event.is_set(),
                timeout=timeout_seconds,
            ) and bool(self._latest_frame)

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
            self._published_at = time.time()
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
        package_name = "cctv_operator_domain_" + hashlib.sha256(str(module_path.parent).encode()).hexdigest()[:12]
        if package_name not in sys.modules:
            spec = importlib.util.spec_from_file_location(
                package_name, module_path.parent / "__init__.py",
                submodule_search_locations=[str(module_path.parent)],
            )
            if spec is None or spec.loader is None:
                break
            package = importlib.util.module_from_spec(spec)
            sys.modules[package_name] = package
            try:
                spec.loader.exec_module(package)
            except Exception:
                sys.modules.pop(package_name, None)
                raise
        module = importlib.import_module(f"{package_name}.{module_name}")
        return getattr(module, function_name)
    raise RuntimeError(f"cctv_operator {module_name} is unavailable")


operator_state = _load_domain_function("dashboard", "operator_state")
_dashboard_html = _load_domain_function("media", "dashboard_html")


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
        self._live_monitor = None

    def start_monitor(self) -> None:
        monitor = _load_domain_function("live_monitor", "LiveMonitor")
        self._live_monitor = monitor(self.run_dir, self.run_id, self.config,
                                     self.preview_stream, self.ui_state)
        self._live_monitor.start()

    def attach_activity_store(self, store: Any) -> None:
        self._activity_store = store

    def sync_mcp_activity(
        self, state: Mapping[str, Any] | None = None, *, now: float | None = None
    ) -> list[dict[str, Any]]:
        if self._activity_store is None:
            return []
        projected = dict(state or self.ui_state())
        events = projected.get("events") if isinstance(projected.get("events"), list) else []
        findings = projected.get("conversation_findings") or []
        published = []
        for event in [*reversed(events), *findings]:
            if not isinstance(event, Mapping):
                continue
            title = " ".join(str(event.get("type") or "Activity observed").split())[:240]
            if title not in {"Operator notice", "Monitoring result", "Possible risk"}:
                continue
            message = str(event.get("summary") or "").strip()[:8_000]
            occurred_at = " ".join(str(event.get("timestamp") or "").split())[:80]
            if not message:
                continue
            digest = event.get("event_id") or hashlib.sha256(
                f"{self.run_id}\0{title}\0{occurred_at}\0{message}".encode()
            ).hexdigest()[:32]
            if self._activity_store.get_record("result", digest, include_staged=False):
                continue
            activity = {
                "schema_version": "mn.mcp.job_activity.v1",
                "event_id": digest,
                "title": title,
                "message": message,
                "occurred_at": occurred_at,
                "source": "cctv_operator",
                "requires_review": title in {"Operator notice", "Possible risk"},
                **({"image": event["image"]} if isinstance(event.get("image"), Mapping) else {}),
                **({"notice_id": event["notice_id"]} if event.get("notice_id") else {}),
                **({"details": event["details"]} if event.get("details") else {}),
            }
            published.append(
                self._activity_store.publish_result(
                    digest,
                    activity,
                    stage="live_activity",
                    summary=f"{title}: {message}"[:2_000],
                    publication_state="final",
                    idempotency_key=f"cctv-activity:{digest}:final",
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
        projection = _load_domain_function("pipeline_status", "pipeline_status")
        safe_state["pipeline"], warning = projection(
            read_json_object(self.run_dir / "person_detector_state.json"),
            read_json_object(self.run_dir / "caption_schedule.json"),
            last_presence=_event_payload(_latest_event(events, "cctv_operator_person_event")))
        if warning:
            safe_state["warning"] = " ".join(dict.fromkeys(filter(None, [safe_state.get("warning"), warning])))
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
        if self._live_monitor is not None:
            self._live_monitor.stop()
        self._stop_event.set()
        self.preview_stream.stop()

    def publish_activity_until_stopped(self) -> None:
        while not self._stop_event.wait(1.0):
            self.ui_state()


class CCTVWebUIServer:
    def __init__(self, service: CCTVWebUIService, *, host: str, port: int) -> None:
        self.service = service
        self._server = ThreadingHTTPServer((host, port), _handler_for(service))
        self._serving = threading.Event()

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._serving.set()
        try:
            self._server.serve_forever(poll_interval=0.5)
        finally:
            self._serving.clear()

    def stop(self) -> None:
        self.service.stop()
        if self._serving.is_set():
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
            preview_config = (service.config.get("web_ui") or {}).get("preview") or {}
            if not service.preview_stream.enabled or preview_config.get("enabled") is False:
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
        domain_tool,
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
    VideoQuestions = _load_domain_function("video_questions", "VideoQuestions")
    video_questions = VideoQuestions(run_dir, run_id, store, service.config)
    server = create_mrtr_mcp_server(
        "CCTV Operator agent",
        instructions=(
            "Inspect the current operator status and activity before answering. "
            "Use get_video_history for past observations and qualified risk predictions. "
            "Use answer_video_question and get_video_summary for text answers from saved Markdown history. "
            "These asynchronous reads never invoke Cosmos or review images. Missing history is explicit. "
            "Use set_monitoring_instruction to change what the current run analyzes. "
            "Use watch_operator_activity for a bounded live wait. A transport receipt "
            "does not acknowledge an operator notice."
        ),
        host=host,
        port=port,
        server_factory=server_factory,
    )

    @domain_tool(server, name="get_operator_status", structured_output=True)
    def get_operator_status(question: str = "") -> dict[str, Any]:
        state = service.ui_state()
        metrics = state["metrics"]
        finding = metrics["latest finding"]
        observed_at = metrics["last analyzed"]
        summary = _load_domain_function("conversation_status", "operator_status_summary")(state)
        return {
            "schema_version": "mn.cctv.operator_status.v1",
            "ready": True,  # Control availability does not depend on a first detection.
            "status": metrics["status"],
            "finding": finding,
            "observed_at": observed_at,
            "summary": summary,
            "metrics": metrics,
            "details": state.get("finding_details", []),
            "understanding": state.get("understanding", {}),
            "pipeline": state.get("pipeline", {}),
            "warning": state.get("warning"),
        }

    @domain_tool(server, name="get_pipeline_benchmarks", structured_output=True)
    def get_pipeline_benchmarks() -> dict[str, Any]:
        benchmarks = _load_domain_function("benchmarks", "Benchmarks")
        return benchmarks(run_dir, service.config).summary()

    @domain_tool(server, name="get_operator_activity", structured_output=True)
    def get_operator_activity(after_revision: int = 0) -> dict[str, Any]:
        service.ui_state()
        try:
            cursor = max(int(after_revision or 0), 0)
        except (TypeError, ValueError) as error:
            raise ValueError("after_revision must be a non-negative integer") from error
        result = store.updates(after_revision=cursor, kinds=["result"], include_staged=False, limit=20)
        # Tool-planning history carries captions; evidence previews travel with
        # the single-event watch and never accumulate in a large tool response.
        for update in result["updates"]:
            update["payload"].pop("image", None)
        return result

    @domain_tool(server, name="get_video_history", structured_output=True)
    def get_video_history(after: str = "", before: str = "") -> dict[str, Any]:
        read_history = _load_domain_function("runtime_memory", "read_video_history")
        return read_history(service.config, run_dir, after=after, before=before)

    @domain_tool(server, name="get_video_summary", structured_output=True)
    def get_video_summary(command_id: str, after: str = "", before: str = "") -> dict[str, Any]:
        return video_questions.submit(command_id, "Summarize what happened in the video, with capture times and uncertainty.",
                                      after=after, before=before, summarize=True)

    @domain_tool(server, name="answer_video_question", structured_output=True)
    def answer_video_question(command_id: str, question: str, after: str = "", before: str = "") -> dict[str, Any]:
        return video_questions.submit(command_id, question, after=after, before=before)

    @domain_tool(server, name="watch_job_activity", structured_output=True)
    async def watch_job_activity(
        after_event_id: str = "",
        wait_seconds: float = 20,
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
            previous = store.get_record("result", cursor, include_staged=False) if cursor else None
            if previous:
                updates = store.updates(after_revision=previous["revision"], kinds=["result"], include_staged=False, limit=1)["updates"]
            else:
                latest = store.latest_record("result", include_staged=False)
                updates = [latest] if latest else []
            activity = updates[0]["payload"] if updates else None
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

    @domain_tool(server, name="acknowledge_operator_notice", structured_output=True)
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

    @domain_tool(server, name="set_monitoring_instruction", structured_output=True)
    def set_monitoring_instruction(
        command_id: str,
        instruction: str = "",
        clear: bool = False,
        analyze_now: bool = True,
    ) -> dict[str, Any]:
        resolved_command_id = str(command_id or "").strip()
        resolved_instruction = " ".join(str(instruction or "").split())[:500]
        if not isinstance(clear, bool) or not isinstance(analyze_now, bool):
            raise ValueError("clear and analyze_now must be booleans")
        clear_enabled = clear
        analyze_now_enabled = analyze_now
        if not resolved_command_id:
            raise ValueError("command_id is required")
        if not clear_enabled and not resolved_instruction:
            raise ValueError("instruction is required unless clear=true")
        sender = runtime_service
        if sender is None:
            from .cctv_operator_mcp import send_monitoring_input

            try:
                accepted = send_monitoring_input(run_dir, {
                    "command_id": resolved_command_id,
                    "instruction": resolved_instruction,
                    "clear": clear_enabled,
                    "analyze_now": analyze_now_enabled,
                })
            except RuntimeError:
                return {"ok": False, "state": "failed", "error": "monitoring control unavailable"}
        else:
            from .cctv_operator_mcp import configured_execution_id

            accepted = sender.send_run_input(
                configured_execution_id(),
                "steer_monitoring",
                {
                    "command_id": resolved_command_id,
                    "instruction": resolved_instruction,
                    "clear": clear_enabled,
                    "analyze_now": analyze_now_enabled,
                },
                idempotency_key=resolved_command_id,
            )
        command_summary = _load_domain_function("conversation_status", "monitoring_command_summary")
        summary = command_summary("accepted")
        store.publish_status(
            "accepted",
            stage="set_monitoring_instruction",
            summary=summary,
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
            "summary": summary,
        }

    @domain_tool(server, name="get_operation_status", structured_output=True)
    def get_operation_status(operation_id: str, kind: Literal["command", "video"] = "command") -> dict[str, Any]:
        if kind == "video":
            return video_questions.status(operation_id)
        resolved_command_id = str(operation_id or "").strip()[:128]
        record = store.get_record("status", resolved_command_id, include_staged=True)
        monitoring = read_monitoring_state(run_dir / "monitoring_state.json")
        state = str((record or {}).get("payload", {}).get("status") or "unknown")
        if monitoring.get("command_id") == resolved_command_id:
            state = "completed"
        observations = read_json_object(run_dir / "cctv_report.json").get("observations") or []
        latest_observation = observations[-1] if observations else {}
        analyzed_revision = int(latest_observation.get("instruction_revision") or 0)
        applied_revision = int(monitoring.get("instruction_revision") or 0)
        analysis_ready = state == "completed" and analyzed_revision == applied_revision and applied_revision > 0
        record_payload = (record or {}).get("payload") or {}
        metadata = record_payload.get("metadata") or {}
        is_monitoring = ((record or {}).get("stage") == "set_monitoring_instruction"
                         or monitoring.get("command_id") == resolved_command_id)
        summary = (record or {}).get("summary", "")
        if is_monitoring and state in {"accepted", "running", "completed"}:
            summary = _load_domain_function("conversation_status", "monitoring_command_summary")(
                state, clear=metadata.get("clear") is True or not monitoring.get("instruction"),
                instruction=monitoring.get("instruction") or "", analysis_ready=analysis_ready,
                finding=latest_observation.get("scene_understanding") or latest_observation.get("summary"))
        return {
            "schema_version": "mn.cctv.command_receipt.v1",
            "command_id": resolved_command_id,
            "state": state,
            "instruction": monitoring.get("instruction") if state == "completed" else None,
            "instruction_revision": (
                monitoring.get("instruction_revision") if state == "completed" else None
            ),
            "analysis_ready": analysis_ready,
            "latest_finding": (latest_observation.get("scene_understanding") or latest_observation.get("summary")) if analysis_ready else None,
            "summary": summary,
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


def _run_operator_mcp(server: Any, listener: socket.socket, lifecycle: dict) -> None:
    import uvicorn

    options = dict(getattr(server, "_mn_http_options", {}))
    options.pop("port", None)
    app = server.streamable_http_app(**options)
    try:
        transport = uvicorn.Server(uvicorn.Config(app, log_level="info", timeout_graceful_shutdown=2))
        lifecycle["server"] = transport
        if not lifecycle["stopped"].is_set():
            transport.run(sockets=[listener])
    finally:
        listener.close()


class OperatorMCPService:
    """The camera's private MCP listeners and activity thread share its lifetime."""

    def __init__(self, service, listener, proxy, lifecycle, threads):
        self.service, self.listener, self.proxy = service, listener, proxy
        self.lifecycle, self.threads = lifecycle, threads

    def is_alive(self):
        return all(worker.is_alive() for worker in self.threads)

    def stop(self):
        self.lifecycle["stopped"].set()
        transport = self.lifecycle.get("server")
        if transport is not None:
            transport.should_exit = True
        self.service._stop_event.set()
        errors = []
        operations = []
        if self.threads[-1].is_alive():
            operations.append(self.proxy.shutdown)
        operations.append(self.proxy.server_close)
        operations.extend(lambda worker=worker: worker.join(timeout=3)
                          for worker in self.threads if worker.ident is not None)
        operations.append(self.listener.close)
        for cleanup in operations:
            try:
                cleanup()
            except Exception as exc:
                errors.append(exc)
        if any(worker.is_alive() for worker in self.threads):
            errors.append(RuntimeError("CCTV private listener thread did not stop"))
        if errors:
            raise RuntimeError("CCTV private listener cleanup failed") from errors[0]


def start_operator_mcp_server(
    service: CCTVWebUIService,
    *,
    job_id: str,
    run_id: str,
    run_dir: Path,
) -> OperatorMCPService:
    """Start the SDK MRTR server on a private, OS-selected owner-node port."""

    from .cctv_operator_mcp import create_mcp_proxy

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
    lifecycle = {"stopped": threading.Event()}
    thread = threading.Thread(
        target=_run_operator_mcp,
        args=(server, listener, lifecycle),
        name="cctv-operator-private-mcp",
        daemon=True,
    )
    activity_thread = threading.Thread(target=service.publish_activity_until_stopped,
        name="cctv-operator-activity", daemon=True)
    proxy_thread = threading.Thread(target=proxy.serve_forever,
        name="cctv-operator-mcp-relay", daemon=True)
    managed = OperatorMCPService(service, listener, proxy, lifecycle,
        [thread, activity_thread, proxy_thread])
    try:
        for worker in managed.threads:
            worker.start()
    except BaseException:
        managed.stop()
        raise
    try:
        relay_port = int(proxy.server_address[1])
        endpoint = {
            "schema_version": "mn.cctv.operator_mcp_endpoint.v1",
            "url": f"http://host.docker.internal:{relay_port}",
            "port": relay_port,
            "token": token,
            "run_id": run_id,
        }
        target = run_dir / CCTV_MCP_ENDPOINT_ARTIFACT
        atomic_write_json(target, endpoint)
    except BaseException:
        managed.stop()
        raise
    return managed
