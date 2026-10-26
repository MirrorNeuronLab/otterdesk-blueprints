"""Camera resource ownership for the SDK monitored-service block."""

import subprocess
import threading
import time
from http.client import HTTPConnection

from mn_sdk.integrations.service_web_ui import claim_service_web_ui
from mn_sdk_web_ui import resolve_web_ui_binding

DEMO_LAUNCHER = "/opt/cctv-demo/start_demo_stream.sh"


def start_demo(config):
    source = config.get("video_source") or {}
    if source.get("profile") == "bundled_demo":
        # The image-owned publisher inherits this service's Core process group.
        # Sampling only probes it and cannot own or stop its descendants.
        subprocess.run(
            [DEMO_LAUNCHER, source["demo_file"]],
            check=True,
            stdout=subprocess.DEVNULL,
            timeout=60,
        )


def start(block, inputs):
    from services import cctv_web_ui as ui

    resources = block.resources
    start_demo(block.config)
    service = ui.CCTVWebUIService(
        run_id=block.run_id, run_dir=block.store.run_dir, config=dict(block.config)
    )
    resources["service"] = service
    resources["mcp"] = ui.start_operator_mcp_server(
        service, job_id=block.job_id, run_id=block.run_id, run_dir=block.store.run_dir
    )
    if not resources["mcp"].is_alive():
        raise RuntimeError("CCTV Operator MCP failed to start")
    service.start_monitor()
    binding = resolve_web_ui_binding(block.config)
    server = ui.CCTVWebUIServer(service, host=binding.host, port=binding.port)
    resources["server"] = server
    worker = threading.Thread(
        target=server.serve_forever, name="cctv-web-ui", daemon=True
    )
    resources["web_thread"] = worker
    worker.start()
    _host, port = server.address
    deadline = time.monotonic() + 10
    while True:
        block.check()
        if _ready(port):
            break
        if time.monotonic() >= deadline or not worker.is_alive():
            raise RuntimeError("CCTV Web UI did not become ready")
        time.sleep(0.1)
    if (
        service.preview_stream.enabled
        and not service.preview_stream.wait_for_first_frame()
    ):
        raise RuntimeError("CCTV Web UI preview did not produce a video frame")
    claim_service_web_ui(
        block,
        title="CCTV Operator",
        url=ui.public_service_url(binding.host, port),
        service_name=ui.WEB_UI_SERVICE_NAME,
        node_id=ui.WEB_UI_NODE_ID,
        http_ports=[port],
        metadata={"upstream": "cctv-operator-docker-worker"},
    )


def _ready(port):
    connection = HTTPConnection("127.0.0.1", port, timeout=1)
    try:
        connection.request("GET", "/health")
        return connection.getresponse().status == 200
    except OSError:
        return False
    finally:
        connection.close()


def health(block, inputs):
    # Person/caption failures retain their existing independent, visible lane
    # health. Losing a required listener fails the owning service as a whole.
    return (
        block.resources["web_thread"].is_alive()
        and block.resources["mcp"].is_alive()
        and _ready(block.resources["server"].address[1])
    )


def cycle(block, inputs):
    return {"status": "listening"}


def stop(block, inputs):
    resources = block.resources
    try:
        if "server" in resources:
            resources["server"].stop()
        elif "service" in resources:
            resources["service"].stop()
    finally:
        try:
            if "mcp" in resources:
                resources["mcp"].stop()
        finally:
            if (
                "web_thread" in resources
                and resources["web_thread"].ident is not None
            ):
                resources["web_thread"].join(timeout=3)
            # The SDK still needs its claim ownership to publish stopped/failed.
            for key in ("service", "mcp", "server", "web_thread"):
                resources.pop(key, None)
