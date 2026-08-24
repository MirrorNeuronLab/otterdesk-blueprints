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
    assert "warehouse-mcp:" in source
    assert "./mcp/robot_control_server.py" in source
    assert "TURTLEBOT_X11_SOCKET:-/dev/null" in source
    assert "TURTLEBOT_XAUTHORITY:-/dev/null" in source
    assert '"9090:9090"' not in source
    assert '"8765:8765"' not in source
    assert "warehouse-video-ui:\n    image: nginx:alpine\n    network_mode: host" in source
