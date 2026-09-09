"""Expose the CCTV DockerWorker's private MCP endpoint to the Job agent."""

from __future__ import annotations

import json
import os
import signal
import secrets
import socket
import struct
import time
from collections.abc import Mapping
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit

CCTV_MCP_ENDPOINT_ARTIFACT = "cctv_operator_mcp_endpoint.json"
CCTV_MCP_PORT = 62009
MCP_REQUEST_LIMIT = 1_048_576
MCP_RESPONSE_LIMIT = 2_097_152
REGISTRATION_TIMEOUT_SECONDS = 60.0
_PRIVATE_UPSTREAM_HOSTS = {"host.docker.internal", "127.0.0.1", "localhost", "::1"}


def configured_run_dir() -> Path:
    value = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if value:
        return Path(value).expanduser()
    root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = str(os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run")
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
        or str(parsed.hostname or "").lower() not in _PRIVATE_UPSTREAM_HOSTS
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    try:
        port = parsed.port
    except ValueError:
        return None
    if port is None or not 1 <= port <= 65_535:
        return None
    endpoint = {"url": url.rstrip("/"), "port": port}
    if value.get("token"):
        endpoint["token"] = str(value["token"])
    return endpoint


def await_endpoint(path: Path, *, timeout_seconds: float = REGISTRATION_TIMEOUT_SECONDS) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        endpoint = read_endpoint(path)
        if endpoint is not None:
            return endpoint
        time.sleep(0.1)
    raise RuntimeError("CCTV Operator MCP did not publish its private endpoint")


def _default_gateway_ipv4(route_path: Path = Path("/proc/net/route")) -> str:
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
    clients = {"127.0.0.1", "::1"}
    gateway = _default_gateway_ipv4(route_path)
    if gateway:
        clients.add(gateway)
    return frozenset(clients)


def create_mcp_proxy(
    endpoint: Mapping[str, Any],
    *,
    host: str = "0.0.0.0",
    port: int = CCTV_MCP_PORT,
    server_factory: Any = ThreadingHTTPServer,
    access_token: str = "",
) -> Any:
    upstream = urlparse(str(endpoint.get("url") or ""))
    if upstream.scheme != "http" or str(upstream.hostname or "").lower() not in _PRIVATE_UPSTREAM_HOSTS:
        raise RuntimeError("CCTV Operator MCP proxy requires a private HTTP upstream")
    upstream_port = upstream.port
    if upstream_port is None:
        raise RuntimeError("CCTV Operator MCP proxy upstream requires a port")
    permitted_clients = allowed_proxy_clients()

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def do_GET(self) -> None:
            self._forward()

        def do_POST(self) -> None:
            self._forward()

        def do_DELETE(self) -> None:
            self._forward()

        def _forward(self) -> None:
            authorized = (
                secrets.compare_digest(str(self.headers.get("X-CCTV-MCP-Token") or ""), access_token)
                if access_token
                else str(self.client_address[0]) in permitted_clients
            )
            if not authorized:
                self._send_json(403, {"error": "forbidden"})
                return
            request_path = urlsplit(self.path).path
            if request_path == "/health" and self.command == "GET":
                try:
                    with socket.create_connection(
                        (str(upstream.hostname), upstream_port), timeout=1
                    ):
                        self._send_json(200, {"status": "ok"})
                except OSError:
                    self._send_json(503, {"status": "error"})
                return
            if request_path not in {"/mcp", "/mcp/"}:
                self._send_json(404, {"error": "not found"})
                return
            try:
                length = int(str(self.headers.get("Content-Length") or "0"))
            except ValueError:
                self._send_json(400, {"error": "invalid content length"})
                return
            if not 0 <= length <= MCP_REQUEST_LIMIT:
                self._send_json(413, {"error": "request too large"})
                return
            body = self.rfile.read(length) if length else None
            headers = {
                key: value
                for key, value in self.headers.items()
                if key.lower() not in {"connection", "content-length", "host", "transfer-encoding", "x-cctv-mcp-token"}
            }
            if endpoint.get("token"):
                headers["X-CCTV-MCP-Token"] = str(endpoint["token"])
            headers["Host"] = f"127.0.0.1:{upstream_port}"
            connection = HTTPConnection(upstream.hostname, upstream_port, timeout=30)
            try:
                connection.request(self.command, self.path, body=body, headers=headers)
                response = connection.getresponse()
                payload = response.read(MCP_RESPONSE_LIMIT + 1)
                if len(payload) > MCP_RESPONSE_LIMIT:
                    self._send_json(502, {"error": "response too large"})
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
                self._send_json(502, {"error": "CCTV Operator MCP is unavailable"})
            finally:
                connection.close()

        def _send_json(self, status: int, value: Mapping[str, Any]) -> None:
            payload = json.dumps(dict(value), separators=(",", ":")).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, _format: str, *_args: Any) -> None:
            return

    return server_factory((host, port), Handler)


def serve_mcp_proxy(endpoint: Mapping[str, Any], **kwargs: Any) -> None:
    create_mcp_proxy(endpoint, **kwargs).serve_forever(poll_interval=0.5)


def main() -> int:
    endpoint = await_endpoint(configured_run_dir() / CCTV_MCP_ENDPOINT_ARTIFACT)
    allocated_port = str(os.environ.get("MN_PORT_CCTV_OPERATOR_MCP") or "").strip()
    if not allocated_port.isdecimal() or not 1 <= int(allocated_port) <= 65_535:
        raise RuntimeError("CCTV Operator MCP requires its runtime-assigned port")
    proxy_port = int(allocated_port)

    def stop(_signum: int, _frame: Any) -> None:
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    serve_mcp_proxy(endpoint, port=proxy_port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
