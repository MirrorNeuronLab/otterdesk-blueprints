from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

from mn_sdk.blueprints import blueprint_definition, read_blueprint

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "ros_amr_controller"
SOURCE = BLUEPRINT / "payloads" / "docker_compose" / "turtlebot-maze"


def _warehouse_node() -> dict:
    manifest = blueprint_definition(read_blueprint(BLUEPRINT / "manifest.json"))
    return next(
        node
        for node in manifest["agents"]["nodes"]
        if node["node_id"] == "warehouse_service"
    )


def test_ros_amr_uses_the_isolated_compose_runner_and_bundled_source():
    node = _warehouse_node()
    config = node["config"]
    compose = config["compose"]

    assert node["resources"]["runtime_driver"] == "docker_compose"
    assert config["runner_module"] == "MirrorNeuron.Runner.DockerCompose"
    assert compose["context"] == "docker_compose/turtlebot-maze"
    assert compose["file"] == "docker-compose.yaml"
    assert compose["env_file"] == "mirrorneuron/warehouse.env"
    assert set(compose["services"]) == {
        "demo-world-warehouse",
        "warehouse-video-server",
        "warehouse-video-ui",
        "rosbridge",
        "warehouse-control-relay",
        "warehouse-navigation-gateway",
        "warehouse-mcp",
    }
    assert (
        "image" not in config
        and "upload_path" not in config
        and "command" not in config
    )
    assert SOURCE.joinpath("docker-compose.yaml").is_file()
    assert SOURCE.joinpath("mirrorneuron/warehouse.env").is_file()
    assert SOURCE.joinpath("mcp/robot_control_server.py").is_file()
    assert not BLUEPRINT.joinpath("turtlebot-maze").exists()
    assert not BLUEPRINT.joinpath("payloads/worker/start_service.sh").exists()
    assert all(
        service["address"] == "@runtime_node_host"
        for service in node["services"]
    )
    defaults = json.loads((BLUEPRINT / "config/default.json").read_text())
    assert "advertise_host" not in defaults["web_ui"]["service"]
    assert "advertise_host" not in defaults["mcp_control"]["service"]


def test_ros_amr_compose_configuration_resolves_with_headless_environment():
    completed = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            "mirrorneuron/warehouse.env",
            "config",
            "--quiet",
        ],
        cwd=SOURCE,
        check=False,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_ros_amr_compose_owns_mcp_and_opt_in_x11_mounts():
    source = SOURCE.joinpath("docker-compose.yaml").read_text(encoding="utf-8")
    dockerfile = SOURCE.joinpath("docker/Dockerfile.gpu").read_text(encoding="utf-8")
    assert "warehouse-mcp:" in source
    assert "./mcp/robot_control_server.py" in source
    assert "TURTLEBOT_X11_SOCKET:-/dev/null" in source
    assert "TURTLEBOT_XAUTHORITY:-/dev/null" in source
    assert '"9090:9090"' not in source
    assert '"8765:8765"' not in source
    assert (
        "warehouse-video-ui:\n    image: nginx:alpine\n    network_mode: host" in source
    )
    assert "COPY --chmod=0755 ./docker/entrypoint.sh /entrypoint.sh" in dockerfile


def test_ros_amr_warehouse_map_uses_a_compact_staged_image():
    map_yaml = SOURCE.joinpath("tb_worlds/maps/warehouse_world_map.yaml").read_text(
        encoding="utf-8"
    )
    map_png = SOURCE.joinpath("tb_worlds/maps/warehouse_world_map.png").read_bytes()
    compose = SOURCE.joinpath("docker-compose.yaml").read_text(encoding="utf-8")

    assert "image: warehouse_world_map.png" in map_yaml
    assert "./tb_worlds/maps/warehouse_world_map.png:" in compose
    assert map_png.startswith(b"\x89PNG\r\n\x1a\n")
    assert int.from_bytes(map_png[16:20], "big") == 1536
    assert int.from_bytes(map_png[20:24], "big") == 1504
    assert len(map_png) < 256 * 1024


def test_ros_amr_dashboard_hides_controls_and_prioritizes_video_layout():
    dashboard = SOURCE.joinpath("web_ui/index.html").read_text(encoding="utf-8")

    assert 'aria-controls="control-panel" aria-expanded="false"' in dashboard
    assert 'id="control-panel" class="control-drawer"' in dashboard
    assert 'class="overhead-card"' in dashboard
    assert dashboard.count('class="camera-card"') == 2
    assert 'const mapTopic = "/global_costmap/costmap"' in dashboard
    assert 'durability: "transient_local"' in dashboard
    assert 'data-topic="/camera/depth/image_visualized"' in dashboard
    assert "snapshot?topic=${topic}" in dashboard
    assert "snapshotTimeoutMilliseconds = 5000" in dashboard


def test_ros_amr_video_pipeline_colorizes_depth_for_the_browser():
    compose = SOURCE.joinpath("docker-compose.yaml").read_text(encoding="utf-8")
    pipeline = SOURCE.joinpath("web_control/video_pipeline.py").read_text(
        encoding="utf-8"
    )

    assert "./web_control/video_pipeline.py:/app/video_pipeline.py:ro" in compose
    assert "command: python3 /app/video_pipeline.py" in compose
    assert 'DEPTH_INPUT_TOPIC = "/camera/depth/image_rect_raw"' in pipeline
    assert 'DEPTH_DISPLAY_TOPIC = "/camera/depth/image_visualized"' in pipeline
    assert 'output.encoding = "rgb8"' in pipeline


def test_ros_amr_declares_job_scoped_bounded_response_agent():
    manifest = blueprint_definition(read_blueprint(BLUEPRINT / "manifest.json"))
    agent = manifest["response_service"]["agent"]

    assert agent["kind"] == "bounded_mcp"
    assert agent["service"] == {
        "name": "ros-amr-controller-mcp",
        "path": "/mcp",
        "required_tags": ["mcp", "robot-control", "ros-amr-controller"],
    }
    assert agent["preflight"] == {
        "required_for_effects": ["motion"],
        "tool": "get_robot_status",
        "arguments": {},
        "required_result": {"connected": True},
    }
    assert set(agent["tools"]["user"]) == {
        "adjust_robot",
        "cancel_navigation",
        "get_robot_status",
        "navigate_to_zone",
    }
    assert set(agent["tools"]["internal"]) == {"get_navigation_operation"}
    assert agent["operations"]["navigate_to_zone"]["timeout_seconds"] == 180
    assert agent["memory"]["types"] == [
        "zone_alias",
        "control_constraint",
        "capability_note",
    ]
    assert manifest["knowledge_rag"]["top_k"] == 2
    assert manifest["knowledge_rag"]["max_context_chars"] == 1_000
    assert "mcp_control" not in manifest["metadata"]
    assert {item["name"] for item in json.loads((BLUEPRINT / "dependencies.json").read_text())["packages"]} >= {
        "mn-python-sdk-job-response",
        "mn-python-sdk-rag",
        "mn-python-sdk-mcp",
    }


def test_ros_amr_sample_profile_and_chat_commands():
    config = json.loads((BLUEPRINT / "config/default.json").read_text())
    ui = json.loads((BLUEPRINT / "extensions/ui.json").read_text())
    guide = ui["setup_guide"]
    assert guide["schema"] == "otterdesk.setup_guide.v1"
    assert guide["sample"]["available"] is True
    assert guide["sample"]["values"]["inputs.payload.scenario"] == config["inputs"]["payload"]["scenario"]
    assert guide["fields"][0]["path"] == "inputs.payload.scenario"
    assert guide["real"]["available"] is False
    assert {"Move the simulated robot to Zone A.", "Stop", "What is the robot's current status?"} <= set(ui["starter_questions"])


def test_ros_amr_navigation_is_correlated_without_breaking_dashboard_commands():
    gateway = SOURCE.joinpath("web_control/navigation_gateway.py").read_text(
        encoding="utf-8"
    )
    server = SOURCE.joinpath("mcp/robot_control_server.py").read_text(encoding="utf-8")

    assert '"kind": "navigate"' in server
    assert '"operation_id": operation_id' in server
    assert '"/warehouse/navigation_operation"' in server
    assert "def get_navigation_operation(operation_id: str)" in server
    assert "json.loads(raw_command)" in gateway
    assert "command = raw_command.lower()" in gateway
    assert '"completed", zone=route, progress="arrived"' in gateway


def test_ros_amr_robot_mcp_exposes_exact_bounded_tool_set():
    source = SOURCE.joinpath("mcp/robot_control_server.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    tools = {
        node.name
        for node in module.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        if any(
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Attribute)
            and isinstance(decorator.func.value, ast.Name)
            and decorator.func.value.id == "mcp"
            and decorator.func.attr == "tool"
            for decorator in node.decorator_list
        )
    }

    assert tools == {
        "adjust_robot",
        "cancel_navigation",
        "get_navigation_operation",
        "get_robot_status",
        "navigate_to_zone",
    }


def test_ros_amr_navigation_operation_matches_its_non_nullable_output_schema():
    source = SOURCE.joinpath("mcp/robot_control_server.py").read_text(encoding="utf-8")

    assert "class NavigationOperation(TypedDict):" in source
    assert '"zone": str(operation.get("zone") or "")' in source
    assert '"progress": str(operation.get("progress") or "")' in source
    assert '"reason": str(operation.get("reason") or "")' in source
    assert '"updated_at": str(operation.get("updated_at") or "")' in source


def test_ros_amr_command_receipts_declare_compact_confirmation_metadata():
    source = SOURCE.joinpath("mcp/robot_control_server.py").read_text(encoding="utf-8")
    specification = BLUEPRINT.joinpath("SPEC.md").read_text(encoding="utf-8")

    assert "class CommandConfirmation(TypedDict, total=False):" in source
    assert '"label": "NAVIGATION COMMAND"' in source
    assert '"label": "CANCEL COMMAND"' in source
    assert '"label": "ADJUSTMENT COMMAND"' in source
    assert "Do not enter Zone C" in specification
    assert "knowledge/learned/active.md" in specification


def test_chat_commands_use_current_response_engine(tmp_path):
    """Exercise this blueprint's declaration through the real shared chat engine."""
    import time
    from mn_sdk_common.response_service import response_agent
    from mn_sdk_job_response import JobResponseEngine

    manifest = blueprint_definition(read_blueprint(BLUEPRINT / "manifest.json"))
    declaration = manifest["response_service"]["agent"]

    class Planner:
        provider = "fake"
        model = "default"

        def completion_json(self, system, user, *, validator=None, **kwargs):
            assert "move to zone A" in user or "stop" in user
            return validator(self.plan)

    class Adapter:
        connected = True

        def __init__(self):
            self.calls = []

        def resolve(self, run_id, service):
            assert service == declaration["service"]
            return {"run_id": run_id}

        def list_tools(self, config):
            return {"status": "ok", "tools": [
                {"name": name, "inputSchema": {"type": "object", "properties": spec["arguments"]}}
                for group in declaration["tools"].values() for name, spec in group.items()
            ]}

        def call(self, config, tool, arguments):
            self.calls.append((tool, arguments))
            result = {"accepted": True}
            if tool == "get_robot_status":
                result = {"connected": self.connected}
            elif tool == "navigate_to_zone":
                result["operation_id"] = "ba72a876-3b23-4206-91d4-f8286b885999"
            elif tool == "get_navigation_operation":
                result = {"state": "completed", **arguments}
            return {"status": "ok", "result": {"structuredContent": result}}

    planner, adapter = Planner(), Adapter()
    engine = JobResponseEngine(
        job_id="ros-chat-test", blueprint_id="ros_amr_controller", job_data_dir=tmp_path / "ros-chat-test",
        manifest=manifest, agent_declaration=response_agent(manifest),
        llm_client=planner, mcp_adapter=adapter,
    )
    engine.warm()
    context = {"identity": {"job_id": engine.job_id}, "state": "running",
               "latest_run": {"run_id": "ros-run", "status": "running"},
               "_active_service_run_id": "ros-run"}
    planner.plan = {"intent": "action", "tool": "navigate_to_zone", "arguments": {"zone": "zone_a"}}
    answer = engine.ask(question="move to zone A", context=context)
    assert adapter.calls[:2] == [("get_robot_status", {}), ("navigate_to_zone", {"zone": "zone_a"})]
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        result = engine.get_turn(answer["turn"]["turn_id"])
        if result["turn"]["state"] == "completed":
            break
        time.sleep(0.02)
    assert result["turn"]["state"] == "completed"

    adapter.connected = False
    adapter.calls.clear()
    blocked = engine.ask(question="move to zone A", context=context)
    assert blocked["effects"][0]["state"] == "blocked"
    assert adapter.calls == [("get_robot_status", {})]

    adapter.calls.clear()
    planner.plan = {"intent": "action", "tool": "cancel_navigation", "arguments": {}}
    stopped = engine.ask(question="stop", context=context)
    assert stopped["turn"]["state"] == "completed"
    assert adapter.calls == [("cancel_navigation", {})]
    assert stopped["effects"][0]["effect"] == "stop"


def test_chat_uses_resolved_model_and_declared_command_descriptions():

    llm = json.loads((BLUEPRINT / "extensions/llm.json").read_text())
    config = json.loads((BLUEPRINT / "config/default.json").read_text())
    response = json.loads((BLUEPRINT / "extensions/response.json").read_text())
    assert llm["configs"]["primary"]["provider"] == "openai_compatible"
    assert llm["configs"]["primary"]["api_base"] == "auto"
    assert "llm" not in config
    tools = response["agent"]["tools"]["user"]
    assert "move to zone A" in tools["navigate_to_zone"]["description"]
    assert tools["cancel_navigation"]["effect"] == "stop"


def test_mcp_server_schemas_match_chat_declaration(monkeypatch):
    import asyncio
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("ros_amr_mcp_test", SOURCE / "mcp/robot_control_server.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, spec.name, module)
    spec.loader.exec_module(module)
    published = {tool.name: tool for tool in asyncio.run(module.mcp.list_tools())}
    declaration = json.loads((BLUEPRINT / "extensions/response.json").read_text())["agent"]
    expected = {name: tool for group in declaration["tools"].values() for name, tool in group.items()}
    assert published.keys() == expected.keys()
    for name, tool in published.items():
        schema = tool.input_schema
        properties = schema["properties"]
        assert properties.keys() == expected[name]["arguments"].keys()
        for argument, contract in expected[name]["arguments"].items():
            assert all(properties[argument][key] == value for key, value in contract.items())
        assert tool.output_schema is not None
