#!/usr/bin/env python3.12
"""Register Microduck's OS-selected listener with the job-scoped Web UI proxy."""

from __future__ import annotations

import json
import os
import socket
import struct
import time
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.parse import urlparse, urlsplit


WEB_UI_ENDPOINT_ARTIFACT = "microduck_web_ui_endpoint.json"
WEB_UI_NODE_ID = "run_microduck_service__block_run_microduck_service_specialist"
WEB_UI_SERVICE_NAME = "microduck-controller-web-ui"
REGISTRATION_TIMEOUT_SECONDS = 60.0
# The sidecar runs inside the Core container. Bind every container interface so
# Docker's host-loopback port publication can reach it; the manifest still
# advertises and health-checks only 127.0.0.1.
MCP_PROXY_HOST = "0.0.0.0"
MCP_PROXY_PORT = int(os.environ.get("MN_PORT_MICRODUCK_MCP", "62008"))
MCP_PROXY_REQUEST_LIMIT = 1_048_576
MCP_PROXY_RESPONSE_LIMIT = 2_097_152
_DOCKER_WORKER_HOST_PREFIX = "mn-dw-"


def default_gateway_ipv4(route_path: Path = Path("/proc/net/route")) -> str:
    """Return the container's IPv4 default gateway, or fail closed."""

    try:
        lines = route_path.read_text(encoding="utf-8").splitlines()[1:]
    except OSError:
        return ""
    for line in lines:
        columns = line.split()
        if len(columns) < 4 or columns[1] != "00000000":
            continue
        try:
            flags = int(columns[3], 16)
            gateway = int(columns[2], 16)
        except ValueError:
            continue
        if flags & 0x2:
            return socket.inet_ntoa(struct.pack("<L", gateway))
    return ""


def allowed_proxy_clients(route_path: Path = Path("/proc/net/route")) -> frozenset[str]:
    """Allow only Core loopback and Docker's host-port forwarding gateway."""

    clients = {"127.0.0.1", "::1"}
    gateway = default_gateway_ipv4(route_path)
    if gateway:
        clients.add(gateway)
    return frozenset(clients)


def upstream_headers(headers: Mapping[str, str], upstream_port: int) -> dict[str, str]:
    """Forward safe request headers with a Host accepted by the private MCP server."""

    forwarded = {
        key: value
        for key, value in headers.items()
        if key.lower() not in {"connection", "content-length", "host", "transfer-encoding"}
    }
    # FastMCP's DNS-rebinding guard accepts loopback. The TCP connection still
    # targets the scheduler-selected DockerWorker DNS name and private port.
    forwarded["Host"] = f"127.0.0.1:{upstream_port}"
    return forwarded


def configured_run_dir() -> Path:
    value = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if value:
        return Path(value).expanduser()
    root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = str(os.environ.get("MN_WORKFLOW_RUN_ID") or os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run")
    return Path(root).expanduser() / run_id if root else Path.cwd() / "runs" / run_id


def read_endpoint(path: Path) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    url = str(value.get("url") or "").strip()
    parsed = urlparse(url)
    if (
        parsed.scheme != "http"
        or not _is_private_proxy_host(parsed.hostname)
        or parsed.username is not None
        or parsed.password is not None
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None or not 1 <= port <= 65_535:
        return None
    return {"url": url.rstrip("/"), "port": port}


def _is_private_proxy_host(host: str | None) -> bool:
    """Allow loopback tests or the generated DockerWorker DNS name only."""

    normalized = str(host or "").strip().lower()
    return normalized in {"127.0.0.1", "::1", "localhost"} or (
        normalized.startswith(_DOCKER_WORKER_HOST_PREFIX)
        and all(character.islower() or character.isdigit() or character == "-" for character in normalized)
    )


def await_endpoint(path: Path, *, timeout_seconds: float = REGISTRATION_TIMEOUT_SECONDS, check: Callable[[], None] = lambda: None) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        check()
        endpoint = read_endpoint(path)
        if endpoint is not None:
            return endpoint
        time.sleep(0.1)
    raise RuntimeError("Microduck web UI did not publish its private endpoint")


def register_endpoint(
    *,
    job_data_dir: Path,
    job_id: str,
    endpoint: dict[str, Any],
    claimer: Callable[..., Any],
) -> None:
    port = int(endpoint["port"])
    # This is the browser simulator's controller UI, not only an informational
    # service page. Keep its root slash for relative static assets and request
    # the browser-control mode that joins the service bridge.
    ui_url = f"{str(endpoint['url']).rstrip('/')}/?control=1"
    claimer(
        job_data_dir,
        job_id=job_id,
        title="Microduck Controller",
        url=ui_url,
        service_name=WEB_UI_SERVICE_NAME,
        node_id=WEB_UI_NODE_ID,
        http_ports=[port],
        websocket_ports=[port],
        metadata={
            "upstream": "microduck-browser-simulator",
        },
    )


def create_mcp_proxy_server(
    endpoint: dict[str, Any],
    *,
    host: str = MCP_PROXY_HOST,
    port: int = MCP_PROXY_PORT,
    server_factory=ThreadingHTTPServer,
) -> ThreadingHTTPServer:
    """Expose the run's private MCP endpoint to the Job response agent only."""

    upstream = urlparse(str(endpoint["url"]))
    if upstream.scheme != "http" or not _is_private_proxy_host(upstream.hostname):
        raise RuntimeError("Microduck MCP proxy requires a private HTTP upstream")
    upstream_port = upstream.port
    if upstream_port is None:
        raise RuntimeError("Microduck MCP proxy upstream requires a port")
    permitted_clients = allowed_proxy_clients()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:  # noqa: N802
            self._forward()

        def do_POST(self) -> None:  # noqa: N802
            self._forward()

        def do_DELETE(self) -> None:  # noqa: N802
            self._forward()

        def _forward(self) -> None:
            if str(self.client_address[0]) not in permitted_clients:
                self._json_error(403, "forbidden")
                return
            request_path = urlsplit(self.path).path
            if request_path not in {"/health", "/mcp", "/mcp/"}:
                self._json_error(404, "not found")
                return
            raw_length = str(self.headers.get("Content-Length") or "0")
            try:
                content_length = int(raw_length)
            except ValueError:
                self._json_error(400, "invalid content length")
                return
            if not 0 <= content_length <= MCP_PROXY_REQUEST_LIMIT:
                self._json_error(413, "request too large")
                return
            body = self.rfile.read(content_length) if content_length else None
            headers = upstream_headers(dict(self.headers.items()), upstream_port)
            connection = HTTPConnection(upstream.hostname, upstream_port, timeout=15)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read(MCP_PROXY_RESPONSE_LIMIT + 1)
                if len(payload) > MCP_PROXY_RESPONSE_LIMIT:
                    self._json_error(502, "upstream response too large")
                    return
                self.send_response(response.status)
                for key, value in response.getheaders():
                    if key.lower() in {"cache-control", "content-type", "mcp-session-id"}:
                        self.send_header(key, value)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                if payload:
                    self.wfile.write(payload)
            except OSError:
                self._json_error(502, "Microduck control service is unavailable")
            finally:
                connection.close()

        def _json_error(self, status: int, message: str) -> None:
            payload = json.dumps({"error": message}, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return server_factory((host, port), Handler)


def serve_mcp_proxy(endpoint, *, on_ready=None, **options):
    """Run the bounded proxy adapter; production uses the shared service block."""
    server = create_mcp_proxy_server(endpoint, **options)
    try:
        if on_ready is not None:
            on_ready()
        server.serve_forever(poll_interval=0.5)
    finally:
        if hasattr(server, "server_close"):
            server.server_close()
