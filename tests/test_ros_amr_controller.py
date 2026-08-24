from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "ros_amr_controller"
SOURCE = BLUEPRINT / "payloads" / "docker_compose" / "turtlebot-maze"


def _warehouse_node() -> dict:
    manifest = json.loads((BLUEPRINT / "manifest.json").read_text(encoding="utf-8"))
    return next(node for node in manifest["agents"]["nodes"] if node["node_id"] == "warehouse_service")


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
    assert "image" not in config and "upload_path" not in config and "command" not in config
    assert SOURCE.joinpath("docker-compose.yaml").is_file()
    assert SOURCE.joinpath("mirrorneuron/warehouse.env").is_file()
    assert SOURCE.joinpath("mcp/robot_control_server.py").is_file()
    assert not BLUEPRINT.joinpath("turtlebot-maze").exists()
    assert not BLUEPRINT.joinpath("payloads/worker/start_service.sh").exists()


def test_ros_amr_compose_configuration_resolves_with_headless_environment():
    completed = subprocess.run(
        ["docker", "compose", "--env-file", "mirrorneuron/warehouse.env", "config", "--quiet"],
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
    assert "warehouse-video-ui:\n    image: nginx:alpine\n    network_mode: host" in source
    assert "COPY --chmod=0755 ./docker/entrypoint.sh /entrypoint.sh" in dockerfile


def test_ros_amr_warehouse_map_uses_a_compact_staged_image():
    map_yaml = SOURCE.joinpath("tb_worlds/maps/warehouse_world_map.yaml").read_text(encoding="utf-8")
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
