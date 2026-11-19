"""Serve the live, read-only hotel workspace through the Job's Web UI proxy."""

import json
import socket
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread

from .layout import floor_plan


FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/hotel.css": ("hotel.css", "text/css; charset=utf-8"),
    "/hotel.js": ("hotel.js", "text/javascript; charset=utf-8"),
    "/floor-plan.js": ("floor-plan.js", "text/javascript; charset=utf-8"),
}
ASSETS = Path(__file__).with_name("web_assets")


def advertised_url(binding, port, environment):
    if environment and environment.get("MN_DOCKER_WORKER_NETWORK_MODE") == "runtime" and not (
        environment.get("MN_BLUEPRINT_WEB_UI_BASE_URL") or environment.get("MN_WEB_UI_PROXY_HOST")
    ):
        # The owner runtime relays HTTP from the Linux host, which cannot
        # resolve names from the Docker bridge's private DNS.
        worker = environment["MN_DOCKER_WORKER_CONTAINER_NAME"]
        environment = {**environment, "MN_WEB_UI_PROXY_HOST": socket.gethostbyname(worker)}
    return binding.advertised_url(port, environment=environment)


class Workspace:
    def __init__(self, host, port, snapshot, preview):
        assets = {path: (mime, (ASSETS / name).read_bytes()) for path, (name, mime) in FILES.items()}
        layout = floor_plan()

        class Handler(BaseHTTPRequestHandler):
            timeout = 5

            def do_GET(self):
                self.respond()

            def do_HEAD(self):
                self.respond()

            def respond(self):
                path = self.path.partition("?")[0]
                if path in assets:
                    mime, body = assets[path]
                elif path == "/status.json":
                    mime = "application/json"
                    body = json.dumps({"layout": layout, **snapshot()}, allow_nan=False).encode()
                elif path == "/cameras.jpg":
                    mime, body = "image/jpeg", preview()
                    if body is None:
                        self.send_error(503, "Waiting for the first camera frame")
                        return
                else:
                    self.send_error(404)
                    return
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                if self.command == "GET":
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass

            def log_message(self, *_args):
                pass

        self.server = ThreadingHTTPServer((host, port), Handler)
        self.port = self.server.server_port
        self.thread = Thread(target=self.server.serve_forever, name="hotel-workspace", daemon=True)
        self.thread.start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
