from __future__ import annotations

import ast
import asyncio
import json
import sys
from pathlib import Path

import pytest
from mn_sdk.model_runtime import required_blueprint_models


ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = ROOT / "microduck_controller" / "payloads"
if str(PAYLOADS) not in sys.path:
    sys.path.insert(0, str(PAYLOADS))

from domain.bridge import BridgeHub
from domain.protocol import (
    ProtocolError,
    compact_navigation_result,
    compact_sensor_state,
    validate_command_id,
    validate_motion_plan,
)
from services.duck_control_service import (
    MOTION_ROUTINES,
    _web_ui_endpoint_artifact,
    read_user_manual,
    service_settings,
    write_final_artifact,
)
from services.microduck_web_ui_registrar import (
    MCP_PROXY_HOST,
    allowed_proxy_clients,
    default_gateway_ipv4,
    read_endpoint,
    register_endpoint,
    serve_mcp_proxy,
    upstream_headers,
)


UUID_A = "00000000-0000-4000-8000-000000000001"
UUID_B = "00000000-0000-4000-8000-000000000002"
UUID_C = "00000000-0000-4000-8000-000000000003"


class Clock:
    def __init__(self) -> None:
        self.value = 0.0

    def __call__(self) -> float:
        return self.value


def raw_state(*, ready: bool = True, locomotion: str = "legs") -> dict:
    return {
        "ready": ready,
        "duck": {
            "x": 1.23456,
            "y": -2.34567,
            "yaw": 0.25,
            "speed": 0.8,
            "mode": "walk",
            "locomotion": locomotion,
            "busy": False,
        },
        "ball": {"active": True, "x": 2.0, "y": 3.0, "distance": 4.0},
    }


def navigation_result(**overrides) -> dict:
    value = {
        "schema_version": "mn.microduck.navigation_result.v1",
        "outcome": "found_ball",
        "elapsed_ms": 4_250,
        "path_length_m": 1.25,
        "forward_ticks": 120,
        "turn_ticks": 30,
        "corrections": 2,
        "final_distance_m": 0.21,
        "final_duck_position": {"x": 1.0, "y": 2.0, "yaw": 0.5},
        "final_ball_position": {"x": 1.2, "y": 2.0},
        "final_speed_mps": 0.04,
        "locomotion": "legs",
    }
    value.update(overrides)
    return value


def test_protocol_rejects_raw_or_unbounded_motion_and_projects_compact_state():
    assert validate_command_id(UUID_A) == UUID_A
    assert validate_motion_plan([{"direction": "forward", "duration_ms": 1_000}]) == [
        {"direction": "forward", "duration_ms": 1_000}
    ]

    with pytest.raises(ProtocolError, match="UUID"):
        validate_command_id("not-a-uuid")
    with pytest.raises(ProtocolError, match="exactly"):
        validate_motion_plan([{"direction": "forward", "duration_ms": 100, "velocity": 3}])
    with pytest.raises(ProtocolError, match="not exceed"):
        validate_motion_plan([{"direction": "forward", "duration_ms": 1_000}] * 6)

    state = compact_sensor_state({**raw_state(), "extra": "discard", "duck": {**raw_state()["duck"], "x": 1.23456789}})
    assert state == {
        "schema_version": "mn.microduck.sensor_state.v1",
        "ready": True,
        "duck": {
            "x": 1.2346,
            "y": -2.3457,
            "yaw": 0.25,
            "speed": 0.8,
            "mode": "walk",
            "locomotion": "legs",
        },
        "ball": {"active": True, "x": 2.0, "y": 3.0, "distance": 4.0},
        "active_command": {"command_id": "", "kind": "", "status": "", "reason": ""},
        "recent_command": {"command_id": "", "kind": "", "status": "", "reason": ""},
    }


def test_bridge_enforces_one_lease_idempotency_busy_gate_and_stop_precedence():
    async def scenario() -> None:
        clock = Clock()
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        hub = BridgeHub(clock=clock)
        assert (await hub.enqueue(command_id=UUID_A, kind="motion_plan", payload={"segments": []}))["reason"] == "browser_not_ready"
        assert await hub.claim("control-tab", send) is True
        assert await hub.claim("spectator-tab", send) is False
        assert await hub.update_state("control-tab", raw_state()) is True

        receipt = await hub.enqueue(
            command_id=UUID_A,
            kind="motion_plan",
            payload={"segments": [{"direction": "forward", "duration_ms": 100}]},
        )
        assert receipt["status"] == "queued"
        assert messages[-1]["command"]["kind"] == "motion_plan"
        assert (await hub.enqueue(
            command_id=UUID_B, kind="reset", payload={}
        ))["reason"] == "browser_busy"
        assert (await hub.enqueue(
            command_id=UUID_A,
            kind="motion_plan",
            payload={"segments": [{"direction": "forward", "duration_ms": 100}]},
        ))["command_id"] == UUID_A
        assert (await hub.enqueue(
            command_id=UUID_A,
            kind="motion_plan",
            payload={"segments": [{"direction": "backward", "duration_ms": 100}]},
        ))["reason"] == "command_id_reused_for_different_effect"

        stop = await hub.enqueue(command_id=UUID_C, kind="stop", payload={})
        assert stop["status"] == "queued"
        assert messages[-1]["command"]["kind"] == "stop"
        assert (await hub.command_status(UUID_A))["status"] == "cancelled"
        state = await hub.state()
        assert state["connection"] == {"connected": True, "control_lease": "active", "state_age_ms": 0}
        assert state["ready"] is True
        assert set(state["duck"]) == {"x", "y", "yaw", "speed", "mode", "locomotion"}
        assert set(state["ball"]) == {"active", "x", "y", "distance"}

    asyncio.run(scenario())


def test_bridge_stale_state_rejects_active_work_and_future_effects():
    async def scenario() -> None:
        clock = Clock()
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        hub = BridgeHub(clock=clock)
        await hub.claim("control-tab", send)
        await hub.update_state("control-tab", raw_state())
        await hub.enqueue(command_id=UUID_A, kind="find_ball", payload={})
        clock.value = 1.01

        state = await hub.state()
        assert state["connection"]["connected"] is False
        assert (await hub.command_status(UUID_A))["reason"] == "browser_state_stale"
        assert (await hub.command_status(UUID_A))["message"] == (
            "I stopped looking for the ball because the browser state became stale."
        )
        await asyncio.sleep(0)
        assert messages[-1]["command"] == {
            "command_id": "system-stop",
            "kind": "stop",
            "payload": {},
        }
        assert (await hub.enqueue(command_id=UUID_B, kind="reset", payload={}))["reason"] == "browser_not_ready"

    asyncio.run(scenario())


def test_navigation_receipts_sanitize_progress_and_result_and_keep_idempotency():
    async def scenario() -> None:
        clock = Clock()
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        hub = BridgeHub(clock=clock)
        await hub.claim("control-tab", send)
        await hub.update_state("control-tab", raw_state())
        queued = await hub.enqueue(command_id=UUID_A, kind="find_ball", payload={})
        assert queued["confirmation"] == {
            "kind": "navigation",
            "label": "NAVIGATION COMMAND",
            "target": "ball",
        }
        assert messages[-1]["command"] == {
            "command_id": UUID_A,
            "kind": "find_ball",
            "payload": {},
        }

        assert await hub.update_command(
            "control-tab",
            {
                "command_id": UUID_A,
                "status": "running",
                "progress": "turning",
                "reason": "",
                "untrusted": "discard",
            },
        )
        running = await hub.command_status(UUID_A)
        assert running["progress"] == "turning"
        assert running["message"] == "I’m turning toward the ball."

        result = navigation_result(extra="discard")
        assert await hub.update_command(
            "control-tab",
            {
                "command_id": UUID_A,
                "status": "completed",
                "progress": "<script>",
                "result": result,
            },
        )
        completed = await hub.command_status(UUID_A)
        assert completed["status"] == "completed"
        assert completed["message"] == "I found the ball! I’m tired, but I made it."
        assert completed["result"] == compact_navigation_result(result)
        assert "extra" not in completed["result"]
        assert (await hub.enqueue(command_id=UUID_A, kind="find_ball", payload={})) == completed

    asyncio.run(scenario())


def test_navigation_rejects_invalid_success_and_reports_observed_failures():
    async def scenario() -> None:
        async def send(_message: dict) -> None:
            return None

        hub = BridgeHub(clock=Clock())
        await hub.claim("control-tab", send)
        await hub.update_state("control-tab", raw_state())
        await hub.enqueue(command_id=UUID_A, kind="find_ball", payload={})
        await hub.update_command(
            "control-tab",
            {
                "command_id": UUID_A,
                "status": "completed",
                "result": navigation_result(final_distance_m=0.8),
            },
        )
        invalid = await hub.command_status(UUID_A)
        assert invalid["status"] == "rejected"
        assert invalid["reason"] == "invalid_navigation_result"
        assert "invalid result" in invalid["message"]

        await hub.enqueue(command_id=UUID_B, kind="find_ball", payload={})
        await hub.update_command(
            "control-tab",
            {
                "command_id": UUID_B,
                "status": "rejected",
                "reason": "ball_not_active",
                "result": navigation_result(
                    outcome="ball_not_active",
                    final_distance_m=None,
                    final_ball_position={"x": None, "y": None},
                ),
            },
        )
        missing = await hub.command_status(UUID_B)
        assert missing["state"] == "failed"
        assert missing["message"] == (
            "I couldn’t find the ball because no ball is active."
        )

    asyncio.run(scenario())


def test_free_play_receipt_locks_background_control_until_stop():
    async def scenario() -> None:
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        hub = BridgeHub(clock=Clock())
        await hub.claim("control-tab", send)
        await hub.update_state("control-tab", raw_state())
        queued = await hub.enqueue(command_id=UUID_A, kind="free_play", payload={})
        assert queued["confirmation"] == {
            "kind": "play",
            "label": "FREE PLAY COMMAND",
            "target": "ball",
        }
        assert messages[-1]["command"]["kind"] == "free_play"
        await hub.update_command(
            "control-tab",
            {"command_id": UUID_A, "status": "running", "progress": "settling"},
        )
        await hub.update_command(
            "control-tab",
            {"command_id": UUID_A, "status": "completed", "reason": ""},
        )

        completed = await hub.command_status(UUID_A)
        assert completed["status"] == "completed"
        assert completed["message"] == (
            "Free play started! I’ll keep finding and kicking the ball until you tell me to stop."
        )
        assert (await hub.enqueue(command_id=UUID_B, kind="reset", payload={}))[
            "reason"
        ] == "browser_busy"

        stop = await hub.enqueue(command_id=UUID_C, kind="stop", payload={})
        assert stop["status"] == "queued"
        assert messages[-1]["command"]["kind"] == "stop"
        await hub.update_command(
            "control-tab",
            {"command_id": UUID_C, "status": "completed", "reason": ""},
        )
        assert (await hub.command_status(UUID_C))["message"] == "All actions stopped."

    asyncio.run(scenario())


def test_stale_state_stops_completed_background_free_play():
    async def scenario() -> None:
        clock = Clock()
        messages: list[dict] = []

        async def send(message: dict) -> None:
            messages.append(message)

        hub = BridgeHub(clock=clock)
        await hub.claim("control-tab", send)
        await hub.update_state("control-tab", raw_state())
        await hub.enqueue(command_id=UUID_A, kind="free_play", payload={})
        await hub.update_command(
            "control-tab",
            {"command_id": UUID_A, "status": "completed", "reason": ""},
        )
        clock.value = 1.01

        assert (await hub.state())["connection"]["connected"] is False
        await asyncio.sleep(0)
        assert messages[-1]["command"] == {
            "command_id": "system-stop",
            "kind": "stop",
            "payload": {},
        }

    asyncio.run(scenario())


def test_service_contract_has_exact_mcp_tools_and_private_proxy_defaults(monkeypatch):
    source = (PAYLOADS / "services" / "duck_control_service.py").read_text(encoding="utf-8")
    module = ast.parse(source)
    factory = next(node for node in module.body if isinstance(node, ast.FunctionDef) and node.name == "create_mcp_server")
    tools = {node.name for node in ast.walk(factory) if isinstance(node, ast.AsyncFunctionDef)}
    assert tools == {
        "get_user_manual",
        "get_duck_state",
        "move_duck",
        "perform_routine",
        "find_ball",
        "free_play",
        "get_command_status",
        "stop_duck",
        "set_locomotion",
        "play_ball_action",
        "reset_simulation",
    }

    monkeypatch.setenv("MN_DOCKER_WORKER_CONTAINER_NAME", "mn-dw-job-example-shared-1234")
    settings = service_settings({"web_ui": {"service": {"host": "127.0.0.1", "listen_host": "0.0.0.0", "port": 8080}}})
    assert settings == {
        "host": "0.0.0.0",
        "port": 8080,
        "public_url": "http://127.0.0.1:8080",
        "proxy_url": "http://mn-dw-job-example-shared-1234:8080",
    }
    monkeypatch.delenv("MN_DOCKER_WORKER_CONTAINER_NAME")
    assert service_settings({}) == {
        "host": "127.0.0.1",
        "port": 0,
        "public_url": "http://127.0.0.1:0",
        "proxy_url": "http://127.0.0.1:0",
    }
    with pytest.raises(RuntimeError, match="trusted_lan_enabled"):
        service_settings({"web_ui": {"service": {"host": "192.168.10.8", "public_url": "http://192.168.10.8:8080"}}})
    assert service_settings({"web_ui": {"service": {"host": "192.168.10.8", "public_url": "http://192.168.10.8:8080", "trusted_lan_enabled": True}}})["public_url"] == "http://192.168.10.8:8080"


def test_mcp_manual_and_named_routines_share_the_bounded_control_contract():
    manual = read_user_manual()

    assert "microduck://manual" in (PAYLOADS / "services" / "duck_control_service.py").read_text(encoding="utf-8")
    assert "`move_duck`" in manual
    assert "`perform_routine`" in manual
    assert "`find_ball`" in manual
    assert "`free_play`" in manual
    assert "Never expand this goal into repeated `move_duck` calls" in manual
    assert '`{"intent":"action","tool":"find_ball","arguments":{}}`' in manual
    assert '`{"intent":"action","tool":"free_play","arguments":{}}`' in manual
    assert "repeated `find_ball` or `play_ball_action` calls" in manual
    assert "Match meaning, not exact wording" in manual
    assert "non-exhaustive example, not a required command string" in manual
    assert "wording variation alone is not ambiguity" in manual
    for paraphrase in (
        "free play now",
        "let's free play",
        "you can free play",
        "go play with the ball",
        "take a little step ahead",
        "could you turn to your right now?",
        "bring out",
        "locate",
        "start over",
        "that's enough",
    ):
        assert paraphrase in manual
    for tool in (
        "get_user_manual",
        "get_duck_state",
        "move_duck",
        "perform_routine",
        "find_ball",
        "free_play",
        "stop_duck",
        "set_locomotion",
        "play_ball_action",
        "reset_simulation",
    ):
        assert f'"tool":"{tool}"' in manual
    assert "One conversation turn may issue at most one effect" in manual
    assert manual == (PAYLOADS / "docker_worker" / "knowledge" / "microduck_user_manual.md").read_text(encoding="utf-8").strip()
    assert set(MOTION_ROUTINES) == {"showcase", "spin_left", "spin_right", "zigzag"}
    for segments in MOTION_ROUTINES.values():
        assert validate_motion_plan(segments) == segments


def test_service_settings_applies_the_scheduler_port_to_the_public_handle(monkeypatch):
    monkeypatch.setenv("MN_PORT_WEB_UI", "62007")

    settings = service_settings(
        {
            "web_ui": {
                "service": {
                    "host": "127.0.0.1",
                    "port": 8080,
                    "public_url": "http://127.0.0.1:8080",
                }
            }
        }
    )

    assert settings == {
        "host": "127.0.0.1",
        "port": 62007,
        "public_url": "http://127.0.0.1:62007",
        "proxy_url": "http://127.0.0.1:62007",
    }


def test_service_binds_an_os_selected_private_port_and_publishes_it_for_the_registrar(tmp_path):
    port = 62007
    _web_ui_endpoint_artifact(
        run_dir=tmp_path,
        proxy_url=f"http://mn-dw-job-example-shared-1234:{port}",
        port=port,
    )

    assert read_endpoint(tmp_path / "microduck_web_ui_endpoint.json") == {
        "url": f"http://mn-dw-job-example-shared-1234:{port}",
        "port": port,
    }


def test_mcp_sidecar_accepts_the_host_loopback_port_forward():
    bound = {}

    class FakeServer:
        def __init__(self, address, _handler):
            bound["address"] = address

        def serve_forever(self, *, poll_interval):
            bound["poll_interval"] = poll_interval

    serve_mcp_proxy(
        {"url": "http://127.0.0.1:8080"},
        server_factory=FakeServer,
    )

    assert MCP_PROXY_HOST == "0.0.0.0"
    assert bound == {"address": ("0.0.0.0", 62008), "poll_interval": 0.5}


def test_mcp_sidecar_allows_only_loopback_and_the_discovered_docker_gateway(tmp_path):
    route = tmp_path / "route"
    route.write_text(
        "Iface Destination Gateway Flags RefCnt Use Metric Mask MTU Window IRTT\n"
        "eth0 00000000 010012AC 0003 0 0 0 00000000 0 0 0\n",
        encoding="utf-8",
    )

    assert default_gateway_ipv4(route) == "172.18.0.1"
    assert allowed_proxy_clients(route) == frozenset(
        {"127.0.0.1", "::1", "172.18.0.1"}
    )

    missing = tmp_path / "missing-route"
    assert default_gateway_ipv4(missing) == ""
    assert allowed_proxy_clients(missing) == frozenset({"127.0.0.1", "::1"})


def test_mcp_sidecar_rewrites_the_upstream_host_for_fastmcp():
    assert upstream_headers(
        {
            "Authorization": "Bearer example",
            "Content-Length": "123",
            "Host": "mn-dw-job-example:46287",
            "Mcp-Session-Id": "session-1",
        },
        46287,
    ) == {
        "Authorization": "Bearer example",
        "Host": "127.0.0.1:46287",
        "Mcp-Session-Id": "session-1",
    }


def test_web_ui_registrar_claims_the_shared_proxy_handle_for_the_private_endpoint(tmp_path):
    calls = []

    def claimer(*args, **kwargs):
        calls.append((args, kwargs))

    register_endpoint(
        job_data_dir=tmp_path / "job_mc-example",
        job_id="job_mc-example",
        endpoint={"url": "http://mn-dw-job-example-shared-1234:62007", "port": 62007},
        claimer=claimer,
    )

    args, kwargs = calls.pop()
    assert args == (tmp_path / "job_mc-example",)
    assert kwargs["job_id"] == "job_mc-example"
    assert kwargs["url"] == "http://mn-dw-job-example-shared-1234:62007/?control=1"
    assert kwargs["http_ports"] == [62007]
    assert kwargs["websocket_ports"] == [62007]
    assert kwargs["metadata"] == {"upstream": "microduck-browser-simulator"}


def test_finalizer_writes_a_terminal_artifact_without_command_replay(tmp_path):
    artifact = write_final_artifact(tmp_path)
    stored = json.loads((tmp_path / "final_artifact.json").read_text(encoding="utf-8"))

    assert artifact == stored
    assert stored["status"] == "service_stopped"
    assert stored["source_refs"] == ["web_ui.json", "duck_service_state.json", "duck_command_history.json"]
    assert "replay" in stored["message"]


def test_docker_worker_context_contains_the_exact_runtime_sources():
    worker = PAYLOADS / "docker_worker"

    def source_files(root: Path) -> dict[str, bytes]:
        return {
            path.relative_to(root).as_posix(): path.read_bytes()
            for path in root.rglob("*")
            if path.is_file()
            and "__pycache__" not in path.parts
            and path.name not in {".DS_Store"}
        }

    for name in ("web_app", "agents", "domain", "knowledge", "services"):
        assert source_files(PAYLOADS / name) == source_files(worker / name)

    assert (PAYLOADS / "requirements.txt").read_bytes() == (worker / "requirements.txt").read_bytes()
    assert not (worker / "web_app" / "node_modules").exists()
    assert not (worker / "web_app" / "dist").exists()


def test_source_manifest_compiles_to_one_service_and_one_finalizer_with_bounded_job_agent():
    from mn_sdk import expand_manifest_source

    blueprint = ROOT / "microduck_controller"
    source = json.loads((blueprint / "manifest.json").read_text(encoding="utf-8"))
    config = json.loads((blueprint / "config" / "default.json").read_text(encoding="utf-8"))
    expanded = expand_manifest_source(source, root_dir=blueprint)
    node_ids = {node["node_id"] for node in expanded["agents"]["nodes"]}

    agent = source["response_service"]["agent"]
    assert source["identity"]["manifest_version"] == "1.4"
    assert source["llm"]["configs"]["primary"]["structured_output_options"] == {"temperature": 0}
    assert source["llm"] == config["llm"]
    responsibilities = " ".join(source["llm"]["responsibilities"])
    assert "semantic intent" in responsibilities
    assert "never exact-match triggers" in responsibilities
    assert "let's free play" in responsibilities
    assert "you can free play" in responsibilities
    assert source["metadata"]["starter_questions"][:3] == [
        "Move forward for a medium step.",
        "Could you locate the ball for me?",
        "Let's free play now—keep chasing and kicking it.",
    ]
    init_review = source["metadata"]["init_config_review"]
    assert init_review["required"] is False
    assert "No configuration confirmation is needed" in init_review["instruction"]
    assert {field["path"] for field in init_review["fields"]} == {
        "inputs.payload.input_folder",
        "web_ui.service.public_url",
        "web_ui.service.trusted_lan_enabled",
        "outputs.folder_path",
    }
    assert agent["kind"] == "bounded_mcp"
    assert agent["service"] == {
        "name": "microduck-controller-mcp",
        "path": "/mcp",
        "required_tags": ["mcp", "robot-control", "microduck-controller"],
    }
    assert agent["preflight"] == {
        "required_for_effects": ["motion", "navigation", "play", "locomotion", "ball", "simulation"],
        "tool": "get_duck_state",
        "arguments": {},
        "required_result": {"connected": True, "ready": True},
    }
    assert set(agent["tools"]["user"]) == {
        "get_user_manual",
        "get_duck_state",
        "move_duck",
        "perform_routine",
        "find_ball",
        "free_play",
        "stop_duck",
        "set_locomotion",
        "play_ball_action",
        "reset_simulation",
    }
    assert set(agent["tools"]["internal"]) == {"get_command_status"}
    assert set(agent["operations"]) == {
        "move_duck",
        "perform_routine",
        "find_ball",
        "free_play",
        "stop_duck",
        "set_locomotion",
        "play_ball_action",
        "reset_simulation",
    }
    assert agent["tools"]["user"]["find_ball"] == {
        "effect": "navigation",
        "arguments": {"command_id": {"type": "string"}},
    }
    assert agent["operations"]["find_ball"] == {
        "id_field": "command_id",
        "poll_tool": "get_command_status",
        "poll_argument": "command_id",
        "poll_interval_ms": 500,
        "timeout_seconds": 40,
    }
    assert agent["tools"]["user"]["free_play"] == {
        "effect": "play",
        "arguments": {"command_id": {"type": "string"}},
    }
    assert agent["operations"]["free_play"] == {
        "id_field": "command_id",
        "poll_tool": "get_command_status",
        "poll_argument": "command_id",
        "poll_interval_ms": 500,
        "timeout_seconds": 40,
    }
    assert source["workflow"]["steps"][0]["run"] == {"definition": "steps.run_microduck_service"}
    assert source["workflow"]["steps"][1]["run"] == {"definition": "steps.finalize_service"}
    assert all("network_mode" not in group["with"] for group in source["workers"]["groups"])
    assert {"run_microduck_service__microduck_service", "finalize_service__finalize"} <= node_ids
    assert "microduck_web_ui_registrar" in expanded["agents"]["entrypoints"]
    service_worker = next(
        node for node in expanded["agents"]["nodes"]
        if node["node_id"] == "run_microduck_service__microduck_service"
    )
    assert "resources" not in service_worker["config"]
    registrar = next(
        node for node in expanded["agents"]["nodes"]
        if node["node_id"] == "microduck_web_ui_registrar"
    )
    assert registrar["config"]["runner_module"] == "MirrorNeuron.Runner.HostLocal"
    assert registrar["config"]["command"] == ["python3.11", "microduck_web_ui_registrar.py"]
    assert registrar["config"]["upload_path"] == "services"
    assert registrar["config"]["upload_as"] == "."
    assert registrar["services"][0]["name"] == "microduck-controller-mcp"
    assert registrar["services"][0]["tags"] == [
        "mcp",
        "robot-control",
        "microduck-controller",
    ]
    assert registrar["services"][0]["meta"]["manual_uri"] == "microduck://manual"
    assert registrar["resources"]["ports"] == [
        {"label": "microduck_mcp", "port": 62008, "protocol": "http"}
    ]
    assert expanded["service"]["run_until"] == "manual_stop"
    dependencies = {item["name"] for item in source["skill_dependencies"]}
    assert dependencies == {"mirrorneuron-web-ui-skill"}
    assert source["llm"]["model"] == "default"
    assert source["llm"]["configs"]["primary"]["provider"] == "openai_compatible"
    assert source["llm"]["configs"]["primary"]["api_base"] == "auto"
    assert config["llm"]["configs"]["primary"]["structured_output_options"] == {"temperature": 0}
    assert "runtime_model" not in source["llm"]["configs"]["primary"]
    assert required_blueprint_models(source, config) == []
    assert source["knowledge_rag"]["knowledge_dir"] == "knowledge"
