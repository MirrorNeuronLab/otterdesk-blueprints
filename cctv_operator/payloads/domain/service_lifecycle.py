"""Direct hooks for the SDK monitored-service block."""

import os
import time

from mn_sdk.integrations.service_web_ui import claim_service_web_ui
from mn_sdk_web_ui import resolve_web_ui_binding

from .operator_service import Operator


def start(block, inputs):
    binding = resolve_web_ui_binding(block.config)
    operator = Operator(config=dict(block.config), job_id=block.job_id, run_id=block.run_id,
                        job_data_dir=block.job_data_dir, run_dir=block.store.run_dir,
                        host=binding.host, port=binding.port,
                        mcp_port=int(os.environ.get("MN_PORT_CCTV_OPERATOR_MCP", "0")))
    block.resources["operator"] = operator
    operator.start()
    deadline = time.monotonic() + 10
    while not operator.healthy():
        block.check()
        if operator.failure or time.monotonic() >= deadline:
            raise RuntimeError("The camera workspace did not become available.")
        time.sleep(.05)
    port = operator.web_socket.getsockname()[1]
    host = binding.host
    node = os.environ.get("MN_EXECUTION_NODE", "")
    if host == "0.0.0.0":
        host = node.rpartition("@")[2] if "@" in node else "127.0.0.1"
    url = os.environ.get("MN_BLUEPRINT_WEB_UI_BASE_URL") or f"http://{host}:{port}"
    claim_service_web_ui(block, title="CCTV co-worker", url=url, service_name="cctv-operator-web-ui",
                         node_id="camera_operator", http_ports=[port],
                         metadata={"analysis_service": "NVIDIA vss-rt-vlm"})


def ready(block, inputs):
    operator = block.resources["operator"]
    if operator.failure:
        raise RuntimeError(operator.failure)
    return operator.analysis.state["status"] == "running"


def health(block, inputs):
    return block.resources["operator"].healthy()


def cycle(block, inputs):
    operator = block.resources["operator"]
    return {"status": operator.analysis.state["status"],
            "total_captions": operator.analysis.state["total_captions"]}


def stop(block, inputs):
    operator = block.resources.pop("operator", None)
    if operator:
        operator.stop()
