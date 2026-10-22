"""Microduck listener and control bindings for the shared service block."""

import threading
from http.client import HTTPConnection
from urllib.parse import urlsplit

from mn_sdk.integrations.service_web_ui import claim_service_web_ui
from mn_sdk_web_ui import probe_web_ui
from services.microduck_web_ui_registrar import (
    WEB_UI_ENDPOINT_ARTIFACT, WEB_UI_NODE_ID, WEB_UI_SERVICE_NAME,
    await_endpoint, create_mcp_proxy_server,
)


def start(block, inputs):
    endpoint = await_endpoint(block.store.run_dir / WEB_UI_ENDPOINT_ARTIFACT, check=block.check)
    server = create_mcp_proxy_server(endpoint)
    block.resources.update(proxy=server, endpoint=endpoint)
    worker = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.1}, daemon=True)
    block.resources["worker"] = worker
    worker.start()
    port = endpoint["port"]
    claim_service_web_ui(
        block, title="Microduck Controller", url=endpoint["url"] + "/?control=1",
        service_name=WEB_UI_SERVICE_NAME, node_id=WEB_UI_NODE_ID,
        http_ports=[port], websocket_ports=[port],
        metadata={"upstream": "microduck-browser-simulator"},
    )


def health(block, inputs):
    if not block.resources["worker"].is_alive():
        return False
    return not block.resources.get("ready") or upstream_healthy(block)


def upstream_healthy(block):
    endpoint = urlsplit(block.resources["endpoint"]["url"])
    connection = HTTPConnection(endpoint.hostname, endpoint.port, timeout=2)
    try:
        connection.request("GET", "/health")
        return connection.getresponse().status == 200
    except OSError:
        return False
    finally:
        connection.close()


def ready(block, inputs):
    available = upstream_healthy(block) and probe_web_ui(block.resources["endpoint"]["url"] + "/?control=1")["ready"]
    block.resources["ready"] = available
    return available


def cycle(block, inputs):
    return {"status": "serving"}


def stop(block, inputs):
    server = block.resources.get("proxy")
    worker = block.resources.get("worker")
    if server is None:
        return
    try:
        if worker is not None and worker.is_alive():
            shutdown = threading.Thread(target=server.shutdown, daemon=True)
            shutdown.start()
            shutdown.join(timeout=3)
            if shutdown.is_alive():
                raise RuntimeError("Microduck control listener did not stop")
            worker.join(timeout=3)
            if worker.is_alive():
                raise RuntimeError("Microduck control listener did not stop")
    finally:
        server.server_close()
