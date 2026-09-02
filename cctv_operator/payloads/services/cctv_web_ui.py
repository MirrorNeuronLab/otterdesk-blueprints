#!/usr/bin/env python3.11
"""Serve the CCTV operator page and claim its job-scoped iframe handle."""

from __future__ import annotations

import importlib.util
import json
import mimetypes
import os
import signal
import subprocess
import threading
import time
import urllib.parse
from collections import deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Iterator, Mapping, Protocol

from mn_live_video_analysis_skill import redact_source_urls
from mn_web_ui_skill import claim_web_ui, mark_web_ui_status, resolve_web_ui_binding


SCRIPT_DIR = Path(__file__).resolve().parent
WEB_UI_NODE_ID = "cctv_web_ui"
WEB_UI_SERVICE_NAME = "cctv-operator-web-ui"
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
                    lambda: self._revision != revision
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


def _load_dashboard_projection() -> Callable[..., dict[str, Any]]:
    for ancestor in (SCRIPT_DIR, *SCRIPT_DIR.parents):
        module_path = ancestor / "domain" / "dashboard.py"
        if not module_path.is_file():
            continue
        spec = importlib.util.spec_from_file_location("cctv_operator_dashboard", module_path)
        if spec is None or spec.loader is None:
            break
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.operator_state
    raise RuntimeError("cctv_operator dashboard projection is unavailable")


operator_state = _load_dashboard_projection()


def load_config() -> dict[str, Any]:
    try:
        decoded = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


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
        return json.loads(redact_source_urls(json.dumps(state)))

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

        def do_GET(self) -> None:  # noqa: N802
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

        def do_POST(self) -> None:  # noqa: N802
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


def main() -> int:
    config = load_config()
    run_id = configured_run_id()
    job_id = str(os.environ.get("MN_JOB_ID") or run_id).strip()
    run_dir = configured_run_dir()
    job_data_dir = configured_job_data_dir(job_id)
    run_dir.mkdir(parents=True, exist_ok=True)
    binding = resolve_web_ui_binding(config)
    service = CCTVWebUIService(run_id=run_id, run_dir=run_dir, config=config)
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


def _dashboard_html() -> str:
    return """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>CCTV Operator</title>
  <style>
    :root {
      color-scheme: dark;
      --canvas: #080b0e;
      --panel: #10151a;
      --panel-raised: #151b21;
      --border: #283139;
      --border-soft: #20282f;
      --ink: #f2f6f5;
      --muted: #8c9a9a;
      --quiet: #697474;
      --signal: #58e0b5;
      --signal-dim: #173c32;
      --amber: #f3b95f;
      --danger: #ff786f;
      --blue: #78a9ff;
      --radius: 14px;
      --mono: "SFMono-Regular", Consolas, "Liberation Mono", monospace;
    }

    * { box-sizing: border-box; }
    html { background: var(--canvas); }
    body {
      margin: 0;
      min-width: 320px;
      background: var(--canvas);
      color: var(--ink);
      font: 14px/1.45 Inter, ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      -webkit-font-smoothing: antialiased;
    }

    .shell { width: min(1480px, 100%); margin: 0 auto; padding: 0 24px 28px; }
    .topbar {
      min-height: 76px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 24px;
      border-bottom: 1px solid var(--border-soft);
    }
    .brand { display: flex; align-items: center; gap: 12px; min-width: 0; }
    .brand-mark {
      width: 38px;
      height: 38px;
      display: grid;
      place-items: center;
      border: 1px solid #345c50;
      border-radius: 10px;
      background: #0c211b;
      color: var(--signal);
    }
    .brand-mark svg { width: 21px; height: 21px; }
    .brand-name { margin: 0; font-size: 16px; font-weight: 680; letter-spacing: -.01em; }
    .brand-subtitle { margin: 2px 0 0; color: var(--muted); font: 11px var(--mono); letter-spacing: .08em; text-transform: uppercase; }
    .connection { display: flex; align-items: center; gap: 9px; color: var(--muted); font: 12px var(--mono); white-space: nowrap; }
    .connection-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--amber); box-shadow: 0 0 0 4px rgba(243,185,95,.1); }
    .connection[data-state="live"] .connection-dot { background: var(--signal); box-shadow: 0 0 0 4px rgba(88,224,181,.1); }
    .connection[data-state="offline"] .connection-dot { background: var(--danger); box-shadow: 0 0 0 4px rgba(255,120,111,.1); }

    main { padding-top: 24px; }
    .panel { background: var(--panel); border: 1px solid var(--border); border-radius: var(--radius); overflow: hidden; }
    .panel-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; padding: 17px 18px 15px; border-bottom: 1px solid var(--border-soft); }
    .eyebrow { margin: 0 0 5px; color: var(--muted); font: 10px var(--mono); letter-spacing: .13em; text-transform: uppercase; }
    h1, h2, h3, p { margin-top: 0; }
    h1 { margin-bottom: 4px; font-size: clamp(24px, 3vw, 34px); line-height: 1.08; letter-spacing: -.035em; }
    h2 { margin-bottom: 0; font-size: 15px; font-weight: 650; letter-spacing: -.01em; }
    .muted { color: var(--muted); }
    .mono { font-family: var(--mono); }

    .operator-panel { display: grid; grid-template-columns: minmax(260px, .72fr) minmax(0, 1.55fr); min-height: 246px; }
    .operator-summary { padding: 22px; border-right: 1px solid var(--border-soft); display: flex; flex-direction: column; }
    .status-line { display: flex; align-items: center; gap: 9px; margin: 13px 0 18px; }
    .status-pulse { width: 9px; height: 9px; border-radius: 50%; background: var(--signal); }
    #operator-status { font-size: 26px; font-weight: 650; letter-spacing: -.035em; }
    .focus-label { margin: auto 0 6px; color: var(--quiet); font: 10px var(--mono); letter-spacing: .12em; text-transform: uppercase; }
    #watch-target { margin: 0; color: #dce5e2; font-size: 13px; }
    .run-ref { margin-top: 14px; color: var(--quiet); font: 11px var(--mono); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .warning { display: none; margin-top: 15px; padding: 10px 12px; border: 1px solid #654b25; border-radius: 9px; background: #211a10; color: #f5cea0; font-size: 12px; }
    .warning.visible { display: block; }

    .event-console { min-width: 0; display: flex; flex-direction: column; }
    .event-console-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 17px 18px 12px; }
    .stream-label { display: flex; align-items: center; gap: 8px; color: var(--muted); font: 10px var(--mono); letter-spacing: .11em; text-transform: uppercase; }
    .live-tag { padding: 4px 7px; border: 1px solid #285646; border-radius: 999px; background: var(--signal-dim); color: var(--signal); font: 9px var(--mono); letter-spacing: .12em; }
    .event-feed { height: 190px; margin: 0; padding: 0 18px 16px; overflow-y: auto; list-style: none; scrollbar-color: #3c494f transparent; }
    .event-item { display: grid; grid-template-columns: 9px minmax(110px,.34fr) 1fr auto; gap: 11px; align-items: baseline; padding: 10px 0; border-top: 1px solid var(--border-soft); }
    .event-item:first-child { border-color: #354139; }
    .event-marker { width: 7px; height: 7px; border-radius: 50%; background: var(--blue); transform: translateY(-1px); }
    .event-item[data-tone="alert"] .event-marker { background: var(--amber); }
    .event-item[data-tone="error"] .event-marker { background: var(--danger); }
    .event-item[data-tone="good"] .event-marker { background: var(--signal); }
    .event-type { color: #dce4e2; font-size: 12px; font-weight: 610; overflow-wrap: anywhere; }
    .event-summary { min-width: 0; color: var(--muted); font-size: 12px; overflow-wrap: anywhere; }
    .event-time { color: var(--quiet); font: 10px var(--mono); white-space: nowrap; }
    .event-empty { display: grid; place-items: center; height: 150px; color: var(--quiet); font: 12px var(--mono); }

    .media-grid { display: grid; grid-template-columns: minmax(0, 1.65fr) minmax(320px, .75fr); gap: 16px; margin-top: 16px; }
    .media-card { min-width: 0; }
    .media-meta { color: var(--quiet); font: 10px var(--mono); text-transform: uppercase; letter-spacing: .08em; }
    .camera-stage { position: relative; aspect-ratio: 16/9; min-height: 280px; background: #030506; overflow: hidden; }
    .camera-stage img { display: block; width: 100%; height: 100%; object-fit: contain; background: #030506; }
    .camera-stage.live-source img { object-fit: cover; }
    .camera-stage::after { content: ""; position: absolute; inset: 0; pointer-events: none; border: 1px solid rgba(255,255,255,.025); }
    .media-badge { position: absolute; left: 14px; top: 14px; display: flex; align-items: center; gap: 7px; padding: 6px 9px; border: 1px solid rgba(255,255,255,.12); border-radius: 7px; background: rgba(5,8,9,.78); color: #edf6f3; font: 10px var(--mono); letter-spacing: .09em; text-transform: uppercase; backdrop-filter: blur(8px); }
    .record-dot { width: 6px; height: 6px; border-radius: 50%; background: #ff554e; box-shadow: 0 0 0 3px rgba(255,85,78,.13); }
    .media-empty { position: absolute; inset: 0; display: grid; place-content: center; gap: 8px; padding: 24px; text-align: center; color: var(--quiet); background: #050708; }
    .media-empty[hidden] { display: none; }
    .media-empty strong { color: var(--muted); font-size: 13px; font-weight: 600; }
    .media-empty span { max-width: 38ch; overflow-wrap: anywhere; }
    .media-footer { display: flex; justify-content: space-between; gap: 16px; padding: 12px 16px; border-top: 1px solid var(--border-soft); color: var(--quiet); font: 10px var(--mono); letter-spacing: .05em; text-transform: uppercase; }

    .telemetry { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; margin-top: 16px; }
    .metric { min-height: 102px; padding: 17px 18px; background: var(--panel-raised); border: 1px solid var(--border); border-radius: 12px; }
    .metric-label { color: var(--quiet); font: 10px var(--mono); letter-spacing: .1em; text-transform: uppercase; }
    .metric-value { display: block; margin-top: 13px; color: var(--ink); font-size: 22px; font-weight: 640; letter-spacing: -.025em; }
    .metric-note { display: block; margin-top: 3px; color: var(--quiet); font-size: 11px; }

    .review-grid { display: grid; grid-template-columns: 1.45fr .75fr; gap: 16px; margin-top: 16px; }
    .finding { padding: 20px 22px 22px; }
    #latest-finding { margin: 14px 0 0; max-width: 78ch; color: #dbe4e1; font-size: 16px; line-height: 1.55; }
    .boundary { padding: 20px 22px; border-color: #4a402b; background: #17150f; }
    .boundary-icon { width: 28px; height: 28px; display: grid; place-items: center; margin-bottom: 18px; border: 1px solid #65562e; border-radius: 8px; color: var(--amber); }
    .boundary p { margin: 8px 0 0; color: #b6ad98; font-size: 12px; }

    @media (max-width: 900px) {
      .operator-panel, .media-grid, .review-grid { grid-template-columns: 1fr; }
      .operator-summary { border-right: 0; border-bottom: 1px solid var(--border-soft); }
      .telemetry { grid-template-columns: repeat(2, minmax(0,1fr)); }
      .camera-stage { min-height: 220px; }
    }
    @media (max-width: 560px) {
      .shell { padding: 0 14px 20px; }
      .topbar { min-height: 68px; }
      .brand-subtitle { display: none; }
      .connection span:last-child { display: none; }
      main { padding-top: 14px; }
      .operator-summary { padding: 18px; }
      .event-item { grid-template-columns: 9px 1fr auto; }
      .event-summary { grid-column: 2 / -1; }
      .telemetry { gap: 8px; }
      .metric { padding: 14px; min-height: 92px; }
      .metric-value { font-size: 19px; }
      .media-footer { flex-direction: column; gap: 4px; }
    }
    @media (prefers-reduced-motion: no-preference) {
      .status-pulse, .record-dot { animation: pulse 2s ease-out infinite; }
      .event-item:first-child { animation: arrive .22s ease-out; }
      @keyframes pulse { 0%,60%,100% { opacity: 1; } 80% { opacity: .38; } }
      @keyframes arrive { from { opacity: 0; transform: translateY(-4px); } to { opacity: 1; transform: none; } }
    }
  </style>
</head>
<body>
  <div class="shell">
    <header class="topbar">
      <div class="brand">
        <div class="brand-mark" aria-hidden="true">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M4 7.5h11.5a2 2 0 0 1 2 2v5a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2v-5a2 2 0 0 1 2-2Z"/><path d="m17.5 10 4.5-2v8l-4.5-2"/><circle cx="7" cy="12" r="1.7"/></svg>
        </div>
        <div>
          <p class="brand-name">CCTV Operator</p>
          <p class="brand-subtitle">Visual intelligence console</p>
        </div>
      </div>
      <div class="connection" id="connection" data-state="connecting" role="status">
        <span class="connection-dot" aria-hidden="true"></span>
        <span id="connection-label">Connecting to operator feed</span>
      </div>
    </header>

    <main>
      <section class="panel operator-panel" aria-labelledby="operator-status">
        <div class="operator-summary">
          <p class="eyebrow">Operator status</p>
          <div class="status-line"><span class="status-pulse" aria-hidden="true"></span><h1 id="operator-status">Starting</h1></div>
          <p class="focus-label">Current monitoring focus</p>
          <p id="watch-target">Loading configured targets…</p>
          <div class="warning" id="warning" role="alert"></div>
          <p class="run-ref" id="run-ref">RUN —</p>
        </div>
        <div class="event-console">
          <div class="event-console-header">
            <div>
              <p class="eyebrow">Live activity</p>
              <h2>Operator event stream</h2>
            </div>
            <span class="live-tag">Live</span>
          </div>
          <ol class="event-feed" id="event-feed" aria-live="polite" aria-relevant="additions">
            <li class="event-empty">Waiting for the first operator event…</li>
          </ol>
        </div>
      </section>

      <section class="media-grid" aria-label="Video monitoring surfaces">
        <article class="panel media-card">
          <div class="panel-heading">
            <div><p class="eyebrow">Source / continuous</p><h2>Live source preview</h2></div>
            <span class="media-meta" id="preview-status">CUDA relay starting</span>
          </div>
          <div class="camera-stage live-source">
            <img id="preview" src="streams/live.mjpg" alt="Live CCTV source preview">
            <div class="media-badge"><span class="record-dot"></span>Live</div>
            <div class="media-empty" id="preview-empty">
              <strong>Connecting to the protected source</strong>
              <span>The MJPEG relay will appear when the media worker is ready.</span>
            </div>
          </div>
          <div class="media-footer"><span>GPU-assisted decode + scale</span><span>Multipart MJPEG</span></div>
        </article>

        <article class="panel media-card">
          <div class="panel-heading">
            <div><p class="eyebrow">Model / sampled</p><h2>Latest analyzed evidence</h2></div>
            <span class="media-meta" id="evidence-time">Awaiting frame</span>
          </div>
          <div class="camera-stage">
            <img id="evidence" alt="Latest frame analyzed by the visual model">
            <div class="media-empty" id="evidence-empty">
              <strong>No analyzed frame yet</strong>
              <span>Evidence appears after the first selected batch completes.</span>
            </div>
          </div>
          <div class="media-footer"><span id="trigger">Trigger —</span><span id="selected-frames">0 selected</span></div>
        </article>
      </section>

      <section class="telemetry" aria-label="Monitoring telemetry">
        <article class="metric"><span class="metric-label">Frames analyzed</span><strong class="metric-value" id="frames-analyzed">0</strong><span class="metric-note">selected evidence</span></article>
        <article class="metric"><span class="metric-label">Target detections</span><strong class="metric-value" id="target-detections">0</strong><span class="metric-note" id="alerts-note">0 awaiting review</span></article>
        <article class="metric"><span class="metric-label">Confidence</span><strong class="metric-value" id="confidence">Waiting</strong><span class="metric-note" id="risk">risk pending</span></article>
        <article class="metric"><span class="metric-label">Model latency</span><strong class="metric-value" id="model-latency">Waiting</strong><span class="metric-note" id="samples-skipped">0 samples skipped</span></article>
      </section>

      <section class="review-grid">
        <article class="panel finding">
          <p class="eyebrow">Most recent assessment</p>
          <h2>Latest finding</h2>
          <p id="latest-finding">Waiting for the first analyzed frame.</p>
        </article>
        <aside class="panel boundary">
          <div class="boundary-icon" aria-hidden="true">!</div>
          <p class="eyebrow">Decision boundary</p>
          <h2>Human confirmation required</h2>
          <p>Confirm every notice against the source video before taking a safety, security, access, or disciplinary action.</p>
        </aside>
      </section>
    </main>
  </div>

  <script>
    const preview = document.querySelector('#preview');
    const previewEmpty = document.querySelector('#preview-empty');
    const evidence = document.querySelector('#evidence');
    const evidenceEmpty = document.querySelector('#evidence-empty');
    const eventFeed = document.querySelector('#event-feed');
    const connection = document.querySelector('#connection');
    let evidenceRevision = '';
    let eventRevision = '';
    let previewState = 'connecting';

    const text = (selector, value) => {
      const node = document.querySelector(selector);
      if (node) node.textContent = String(value ?? '—');
    };

    function eventTone(type) {
      const value = String(type || '').toLowerCase();
      if (value.includes('error') || value.includes('failed')) return 'error';
      if (value.includes('notice') || value.includes('alert') || value.includes('delayed')) return 'alert';
      if (value.includes('ready') || value.includes('completed') || value.includes('observed')) return 'good';
      return 'info';
    }

    function displayTime(value) {
      if (!value || value === 'waiting') return 'now';
      const parsed = new Date(value);
      if (Number.isNaN(parsed.valueOf())) return String(value).slice(0, 16);
      return parsed.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }

    function renderEvents(events) {
      const list = Array.isArray(events) ? events : [];
      const revision = JSON.stringify(list.slice(0, 12));
      if (revision === eventRevision) return;
      eventRevision = revision;
      eventFeed.replaceChildren();
      if (!list.length) {
        const empty = document.createElement('li');
        empty.className = 'event-empty';
        empty.textContent = 'The operator feed is connected and awaiting activity.';
        eventFeed.append(empty);
        return;
      }
      list.slice(0, 32).forEach(event => {
        const item = document.createElement('li');
        item.className = 'event-item';
        item.dataset.tone = eventTone(event.type);
        const marker = document.createElement('span');
        marker.className = 'event-marker';
        marker.setAttribute('aria-hidden', 'true');
        const type = document.createElement('span');
        type.className = 'event-type';
        type.textContent = event.type || 'Runtime event';
        const summary = document.createElement('span');
        summary.className = 'event-summary';
        summary.textContent = event.summary || 'State updated.';
        const timestamp = document.createElement('time');
        timestamp.className = 'event-time';
        timestamp.textContent = displayTime(event.timestamp);
        item.append(marker, type, summary, timestamp);
        eventFeed.append(item);
      });
      eventFeed.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function applyState(state) {
      const metrics = state && state.metrics ? state.metrics : {};
      text('#operator-status', metrics.status || 'Starting');
      text('#watch-target', metrics['watch target'] || 'Default visual targets');
      text('#run-ref', 'RUN ' + (metrics.run || '—'));
      text('#frames-analyzed', metrics['frames analyzed'] ?? 0);
      text('#target-detections', metrics['target detections'] ?? 0);
      text('#alerts-note', (metrics['alerts to review'] ?? 0) + ' awaiting review');
      text('#confidence', metrics.confidence || 'Waiting');
      text('#risk', String(metrics.risk || 'waiting') + ' risk');
      text('#model-latency', metrics['model latency'] || 'Waiting');
      text('#samples-skipped', (metrics['samples skipped'] ?? 0) + ' samples skipped');
      text('#latest-finding', metrics['latest finding'] || 'Waiting for the first analyzed frame.');
      text('#trigger', 'Trigger ' + (metrics['latest trigger'] || '—'));
      text('#selected-frames', (metrics['selected frames'] ?? 0) + ' selected');
      previewState = String(metrics.preview || 'connecting');
      text('#preview-status', previewState.replaceAll('_', ' '));
      text('#evidence-time', metrics['last analyzed'] === 'waiting' ? 'Awaiting frame' : displayTime(metrics['last analyzed']));

      const warning = document.querySelector('#warning');
      warning.textContent = state.warning || '';
      warning.classList.toggle('visible', Boolean(state.warning));
      renderEvents(state.events);

      const nextEvidenceRevision = String(metrics['last analyzed'] || '');
      if (nextEvidenceRevision && nextEvidenceRevision !== 'waiting' && nextEvidenceRevision !== evidenceRevision) {
        evidenceRevision = nextEvidenceRevision;
        evidence.src = 'artifacts/latest_analyzed_frame.jpg?v=' + encodeURIComponent(nextEvidenceRevision);
      }
    }

    preview.addEventListener('load', () => { previewEmpty.hidden = true; });
    preview.addEventListener('error', () => {
      previewEmpty.hidden = false;
      if (previewState !== 'disabled') {
        text('#preview-status', 'reconnecting');
        window.setTimeout(() => { preview.src = 'streams/live.mjpg?retry=' + Date.now(); }, 1500);
      }
    });
    evidence.addEventListener('load', () => { evidenceEmpty.hidden = true; });
    evidence.addEventListener('error', () => { evidenceEmpty.hidden = false; });

    const operatorEvents = new EventSource('streams/operator-events');
    operatorEvents.addEventListener('operator-state', event => {
      try { applyState(JSON.parse(event.data)); } catch { /* keep the prior valid state */ }
    });
    operatorEvents.onopen = () => {
      connection.dataset.state = 'live';
      text('#connection-label', 'Operator feed connected');
    };
    operatorEvents.onerror = () => {
      connection.dataset.state = 'offline';
      text('#connection-label', 'Operator feed reconnecting');
    };
  </script>
</body>
</html>"""


if __name__ == "__main__":
    raise SystemExit(main())
