from __future__ import annotations

import ast
import subprocess
from pathlib import Path

from mn_sdk.blueprints import blueprint_definition, read_blueprint

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT.parent / "mn-blueprints" / "ros_amr_controller"
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
    assert {item["name"] for item in manifest["skill_dependencies"]} >= {
        "mirrorneuron-job-response-skill",
        "mirrorneuron-rag-skill",
        "mirrorneuron-mcp-client-skill",
    }


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
