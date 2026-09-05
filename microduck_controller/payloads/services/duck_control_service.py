#!/usr/bin/env python3.11
"""Serve the bundled simulator, browser lease bridge, and bounded MCP tools."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import os
import re
import socket
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlparse, urlunparse

SERVICE_ROOT = Path(__file__).resolve().parents[1]
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

from domain.bridge import BridgeHub
from domain.protocol import (
    ProtocolError,
    validate_ball_action,
    validate_command_id,
    validate_locomotion,
    validate_motion_plan,
)


WEB_UI_ARTIFACT = "web_ui.json"
WEB_UI_ENDPOINT_ARTIFACT = "microduck_web_ui_endpoint.json"
SERVICE_STATE_ARTIFACT = "duck_service_state.json"
COMMAND_HISTORY_ARTIFACT = "duck_command_history.json"
# ``0`` delegates the private listener port to the OS.  The HostLocal Web UI
# registrar then publishes the resolved endpoint to MirrorNeuron's job-scoped
# proxy; no end user needs to know this port.
DEFAULT_PORT = 0
MANUAL_PATH = SERVICE_ROOT / "knowledge" / "microduck_user_manual.md"
MOVE_DURATIONS_MS = {"short": 250, "medium": 500, "long": 1_000}
MOTION_ROUTINES = {
    "showcase": [
        {"direction": "forward", "duration_ms": 500},
        {"direction": "turn_left", "duration_ms": 350},
        {"direction": "turn_right", "duration_ms": 700},
        {"direction": "backward", "duration_ms": 500},
    ],
    "spin_left": [
        {"direction": "turn_left", "duration_ms": 1_000},
        {"direction": "turn_left", "duration_ms": 1_000},
    ],
    "spin_right": [
        {"direction": "turn_right", "duration_ms": 1_000},
        {"direction": "turn_right", "duration_ms": 1_000},
    ],
    "zigzag": [
        {"direction": "forward", "duration_ms": 500},
        {"direction": "turn_left", "duration_ms": 300},
        {"direction": "forward", "duration_ms": 500},
        {"direction": "turn_right", "duration_ms": 300},
    ],
}
_DNS_HOST_RE = re.compile(r"(?=.{1,253}\Z)[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\Z")


def load_config() -> dict[str, Any]:
    try:
        decoded = json.loads(os.environ.get("MN_BLUEPRINT_CONFIG_JSON", "{}"))
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


def configured_run_dir() -> Path:
    value = str(os.environ.get("MN_RUN_DIR") or "").strip()
    if value:
        return Path(value).expanduser()
    root = str(os.environ.get("MN_RUNS_ROOT") or "").strip()
    run_id = str(os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run")
    return Path(root).expanduser() / run_id if root else Path.cwd() / "runs" / run_id


def service_settings(config: Mapping[str, Any]) -> dict[str, Any]:
    web_ui = config.get("web_ui") if isinstance(config.get("web_ui"), Mapping) else {}
    service = web_ui.get("service") if isinstance(web_ui.get("service"), Mapping) else {}
    # The service stays inside the DockerWorker's runtime network.  The shared
    # job UI proxy reaches it through that worker's unique Docker DNS name;
    # users only ever receive the job-scoped iframe URL.
    host = str(
        os.environ.get("MN_PORT_WEB_UI_HOST")
        or service.get("listen_host")
        or "127.0.0.1"
    )
    allocated_port = str(os.environ.get("MN_PORT_WEB_UI") or "").strip()
    raw_port = allocated_port or service.get("port") or DEFAULT_PORT
    try:
        port = int(raw_port)
    except (TypeError, ValueError) as error:
        raise RuntimeError("Microduck Controller requires a numeric web UI port") from error
    if not 0 <= port <= 65_535:
        raise RuntimeError("Microduck Controller web UI port must be between 0 and 65535")
    public_url = str(service.get("public_url") or "").strip().rstrip("/")
    public_host = str(
        service.get("public_host") or service.get("host") or "127.0.0.1"
    ).strip()
    if public_url and allocated_port:
        public_url = _replace_url_port(public_url, port)
    elif not public_url:
        public_url = f"http://{public_host}:{port}"
    configured_host = str(service.get("host") or "127.0.0.1").strip()
    public_host = urlparse(public_url).hostname or ""
    if not bool(service.get("trusted_lan_enabled")) and (
        not _is_loopback_host(configured_host) or not _is_loopback_host(public_host)
    ):
        raise RuntimeError(
            "non-loopback publication requires web_ui.service.trusted_lan_enabled=true"
        )
    proxy_host = _proxy_host(service, fallback=public_host)
    return {
        "host": host,
        "port": port,
        "public_url": public_url,
        "proxy_url": _replace_url_host_and_port(public_url, proxy_host, port),
    }


def _replace_url_port(value: str, port: int) -> str:
    """Keep a configured public URL's host/path while applying an allocation port."""

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return value
    host = parsed.hostname
    display_host = f"[{host}]" if ":" in host else host
    return urlunparse(
        (
            parsed.scheme,
            f"{display_host}:{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    ).rstrip("/")


def _replace_url_host_and_port(value: str, host: str, port: int) -> str:
    """Keep a configured URL's path while applying the proxy-only authority."""

    parsed = urlparse(value)
    if not parsed.scheme or not parsed.hostname:
        return value
    display_host = f"[{host}]" if ":" in host else host
    return urlunparse(
        (
            parsed.scheme,
            f"{display_host}:{port}",
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    ).rstrip("/")


def _proxy_host(service: Mapping[str, Any], *, fallback: str) -> str:
    """Return the internal DNS name consumed by the job UI proxy only."""

    value = str(
        os.environ.get("MN_WEB_UI_PROXY_HOST")
        or service.get("proxy_host")
        or os.environ.get("MN_DOCKER_WORKER_CONTAINER_NAME")
        or fallback
    ).strip().strip("[]").lower()
    if _is_loopback_host(value) or _DNS_HOST_RE.fullmatch(value):
        return value
    raise RuntimeError("Microduck Controller requires a valid internal Web UI proxy host")


def _is_loopback_host(value: str) -> bool:
    host = str(value or "").strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def _safe_run_id() -> str:
    return str(os.environ.get("MN_RUN_ID") or os.environ.get("MN_JOB_ID") or "run")[:160]


def _service_artifact(
    *,
    run_dir: Path,
    public_url: str,
    state: dict[str, Any],
    history: list[dict[str, Any]],
) -> None:
    _write_json(
        run_dir / SERVICE_STATE_ARTIFACT,
        {
            "schema_version": "mn.microduck.service_state.v1",
            "run_id": _safe_run_id(),
            "web_ui_url": public_url + "/?control=1",
            "mcp_url": public_url + "/mcp",
            "bridge_path": "/bridge",
            "connection": {"browser_connected": bool(state.get("session_connected"))},
            "sensor_state": state.get("sensor_state") or {},
            "active_command_id": state.get("active_command_id") or "",
        },
    )
    _write_json(
        run_dir / COMMAND_HISTORY_ARTIFACT,
        {
            "schema_version": "mn.microduck.command_history.v1",
            "run_id": _safe_run_id(),
            "commands": history[-100:],
        },
    )


def _web_ui_artifact(*, run_dir: Path, public_url: str) -> None:
    _write_json(
        run_dir / WEB_UI_ARTIFACT,
        {
            "schema_version": "mn.blueprint.web_ui.v1",
            "run_id": _safe_run_id(),
            "title": "Microduck Controller",
            "url": public_url + "/?control=1",
            "service_name": "microduck-controller",
            "mcp_url": public_url + "/mcp",
            "health_url": public_url + "/health",
        },
    )


def _web_ui_endpoint_artifact(*, run_dir: Path, proxy_url: str, port: int) -> None:
    """Publish the selected internal endpoint for the job UI registrar."""

    _write_json(
        run_dir / WEB_UI_ENDPOINT_ARTIFACT,
        {
            "schema_version": "mn.microduck.web_ui_endpoint.v1",
            "run_id": _safe_run_id(),
            "url": proxy_url,
            "port": port,
            "health_url": proxy_url + "/health",
            "mcp_url": proxy_url + "/mcp",
            "bridge_path": "/bridge",
        },
    )


def _open_listener(host: str, port: int) -> tuple[socket.socket, int]:
    """Reserve the exact port handed to Uvicorn, including the OS-selected port."""

    family = socket.AF_INET6 if ":" in host.strip("[]") else socket.AF_INET
    listener = socket.socket(family, socket.SOCK_STREAM)
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        listener.bind((host, port))
        listener.listen(socket.SOMAXCONN)
    except Exception:
        listener.close()
        raise
    return listener, int(listener.getsockname()[1])


def write_final_artifact(run_dir: Path) -> dict[str, Any]:
    """Write the terminal record without retaining or replaying control state."""

    artifact = {
        "schema_version": "mn.microduck.service_result.v1",
        "run_id": _safe_run_id(),
        "status": "service_stopped",
        "source_refs": [
            WEB_UI_ARTIFACT,
            SERVICE_STATE_ARTIFACT,
            COMMAND_HISTORY_ARTIFACT,
        ],
        "message": "The browser-backed Microduck service was deliberately stopped; no command is replayed.",
    }
    _write_json(run_dir / "final_artifact.json", artifact)
    return artifact


def read_user_manual() -> str:
    """Read the authoritative manual shared by MCP and Job RAG."""

    try:
        manual = MANUAL_PATH.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise RuntimeError("Microduck MCP user manual is unavailable") from error
    if not manual:
        raise RuntimeError("Microduck MCP user manual is empty")
    return manual


def _state_summary(state: Mapping[str, Any]) -> str:
    connection = state.get("connection") if isinstance(state.get("connection"), Mapping) else {}
    if connection.get("connected") is not True:
        return "The Microduck browser control tab is not connected."
    if state.get("ready") is not True:
        return "The Microduck browser is connected but the simulation is not ready."
    duck = state.get("duck") if isinstance(state.get("duck"), Mapping) else {}
    locomotion = str(duck.get("locomotion") or "unknown")
    return f"Microduck is ready in {locomotion} mode."


def create_mcp_server(hub: BridgeHub):
    """Create the MCP projection without importing server packages during tests."""

    from mcp.server.fastmcp import FastMCP

    mcp = FastMCP(
        "Microduck Controller",
        instructions=(
            "Read the microduck://manual resource or call get_user_manual for the "
            "authoritative control contract. Control only the connected browser-based "
            "Microduck simulation. Call get_duck_state before an effect, use a fresh UUID "
            "for each effect, and call stop_duck if the operator asks to stop. Never infer "
            "completed movement from an accepted receipt; inspect command status or state. "
            "Match requests by semantic intent rather than exact wording. Treat examples as "
            "non-exhaustive, ignore polite or conversational framing when intent is clear, "
            "and clarify only material ambiguity. Map paraphrases for movement, routines, "
            "locomotion, ball actions, reset, stop, state, and the manual to their declared tools. "
            "Map requests to find, seek, approach, or go to the ball to find_ball, and never "
            "expand that goal into repeated move_duck calls. Map free-play requests, including "
            "'free play now', 'let's free play', and 'you can free play', to one free_play call; "
            "it keeps finding and kicking until stop_duck is called."
        ),
        stateless_http=True,
        json_response=True,
    )

    @mcp.resource("microduck://manual")
    def microduck_user_manual_resource() -> str:
        """Return the authoritative natural-language and tool-use manual."""

        return read_user_manual()

    @mcp.tool()
    async def get_user_manual() -> dict[str, Any]:
        """Read capabilities, limits, safety rules, and language-to-tool examples."""

        return {
            "schema_version": "mn.microduck.user_manual.v1",
            "summary": "Microduck supports bounded movement, goal-directed ball navigation, continuous free play, routines, locomotion, ball actions, reset, stop, and live state inspection.",
            "manual": read_user_manual(),
        }

    @mcp.tool()
    async def get_duck_state() -> dict[str, Any]:
        """Read compact, fresh simulator state without changing the duck."""

        state = await hub.state()
        return {
            **state,
            "connected": state["connection"]["connected"],
            "summary": _state_summary(state),
        }

    @mcp.tool()
    async def move_duck(
        command_id: str,
        direction: Literal["forward", "backward", "turn_left", "turn_right"],
        duration: Literal["short", "medium", "long"],
    ) -> dict[str, Any]:
        """Move once in a bounded direction for 250, 500, or 1000 milliseconds."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="motion_plan",
            payload={"direction": direction, "duration": duration},
            validate=lambda: {
                "segments": validate_motion_plan(
                    [{"direction": direction, "duration_ms": MOVE_DURATIONS_MS[duration]}]
                ),
                "move": {"direction": direction, "duration": duration},
            },
        )

    @mcp.tool()
    async def perform_routine(
        command_id: str,
        routine: Literal["showcase", "spin_left", "spin_right", "zigzag"],
    ) -> dict[str, Any]:
        """Run one named, predefined motion routine with a maximum five-second duration."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="motion_plan",
            payload={"routine": routine},
            validate=lambda: {
                "segments": validate_motion_plan(MOTION_ROUTINES[routine]),
                "routine": routine,
            },
        )

    @mcp.tool()
    async def find_ball(command_id: str) -> dict[str, Any]:
        """Approach the active ball with bounded closed-loop simulator navigation."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="find_ball",
            payload={},
            validate=lambda: {},
        )

    @mcp.tool()
    async def free_play(command_id: str) -> dict[str, Any]:
        """Keep finding and alternately kicking the active ball until stop_duck is called."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="free_play",
            payload={},
            validate=lambda: {},
        )

    @mcp.tool()
    async def get_command_status(command_id: str) -> dict[str, Any]:
        """Read the latest receipt for one MCP command UUID."""

        try:
            return await hub.command_status(validate_command_id(command_id))
        except ProtocolError as error:
            return _invalid_receipt(command_id, "unknown", str(error))

    @mcp.tool()
    async def stop_duck(command_id: str) -> dict[str, Any]:
        """Cancel all remote movement, free play, and any in-progress remote kick."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="stop",
            payload={},
            validate=lambda: {},
        )

    @mcp.tool()
    async def set_locomotion(
        command_id: str, locomotion: Literal["legs", "rollers"]
    ) -> dict[str, Any]:
        """Switch the connected simulator between legged and roller locomotion."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="set_locomotion",
            payload={"locomotion": locomotion},
            validate=lambda: {"locomotion": validate_locomotion(locomotion)},
        )

    @mcp.tool()
    async def play_ball_action(
        command_id: str,
        action: Literal["spawn_ball", "kick_left", "kick_right"],
    ) -> dict[str, Any]:
        """Spawn the local ball or execute a left/right leg kick when the simulator is ready."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="ball_action",
            payload={"action": action},
            validate=lambda: {"action": validate_ball_action(action)},
        )

    @mcp.tool()
    async def reset_simulation(command_id: str) -> dict[str, Any]:
        """Reset the connected browser simulation to its deterministic initial state."""

        return await _enqueue(
            hub,
            command_id=command_id,
            kind="reset",
            payload={},
            validate=lambda: {},
        )

    return mcp


async def _enqueue(
    hub: BridgeHub,
    *,
    command_id: Any,
    kind: str,
    payload: Mapping[str, Any],
    validate,
) -> dict[str, Any]:
    try:
        normalized_id = validate_command_id(command_id)
        normalized_payload = validate()
    except ProtocolError as error:
        return _invalid_receipt(command_id, kind, str(error))
    return await hub.enqueue(
        command_id=normalized_id,
        kind=kind,
        payload=normalized_payload,
    )


def _invalid_receipt(command_id: Any, kind: str, reason: str) -> dict[str, Any]:
    return {
        "schema_version": "mn.microduck.command_receipt.v1",
        "command_id": str(command_id or "")[:64],
        "kind": kind,
        "status": "rejected",
        "state": "failed",
        "ok": False,
        "accepted": False,
        "reason": reason,
        "message": f"Command was rejected: {reason}.",
    }


def create_app(
    *,
    static_dir: Path,
    run_dir: Path,
    public_url: str,
    hub: BridgeHub | None = None,
):
    """Build one Starlette application containing static UI, WebSocket, and MCP routes."""

    from starlette.responses import JSONResponse
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles
    from starlette.websockets import WebSocket, WebSocketDisconnect

    state_writer = lambda state, history: _service_artifact(
        run_dir=run_dir,
        public_url=public_url,
        state=state,
        history=history,
    )
    bridge = hub or BridgeHub(on_change=state_writer)
    mcp = create_mcp_server(bridge)
    app = mcp.streamable_http_app()

    async def health(_request):
        snapshot = await bridge.state()
        return JSONResponse(
            {
                "status": "ok",
                "browser_connected": snapshot["connection"]["connected"],
                "ready": snapshot["ready"],
            }
        )

    async def bridge_socket(websocket: WebSocket) -> None:
        await websocket.accept()
        session_id = ""
        try:
            hello = await asyncio.wait_for(websocket.receive_json(), timeout=5)
            if not isinstance(hello, Mapping) or hello.get("type") != "hello":
                await websocket.close(code=1008, reason="expected hello")
                return
            if hello.get("control_mode") is not True:
                await websocket.send_json(
                    {"type": "lease", "accepted": False, "reason": "control_mode_required"}
                )
                return
            session_id = str(hello.get("session_id") or "")
            if not session_id:
                await websocket.close(code=1008, reason="session_id required")
                return
            accepted = await bridge.claim(session_id, websocket.send_json)
            await websocket.send_json(
                {
                    "type": "lease",
                    "accepted": accepted,
                    "reason": "" if accepted else "control_lease_already_held",
                }
            )
            if not accepted:
                # Keep spectators connected so the UI can report that the
                # control lease belongs to another tab.  Their messages are
                # deliberately ignored and they never become the bridge
                # authority for this connection.
                while True:
                    await websocket.receive()
            while True:
                message = await websocket.receive_json()
                if not isinstance(message, Mapping):
                    continue
                if message.get("type") == "state":
                    await bridge.update_state(session_id, message.get("state"))
                elif message.get("type") == "command_update":
                    await bridge.update_command(session_id, message)
        except (WebSocketDisconnect, asyncio.TimeoutError):
            pass
        finally:
            if session_id:
                await bridge.disconnect(session_id)

    _web_ui_artifact(run_dir=run_dir, public_url=public_url)
    state_writer({"session_connected": False, "sensor_state": {}, "active_command_id": ""}, [])
    app.router.routes.insert(0, Route("/health", health, methods=["GET"]))
    app.router.routes.insert(1, WebSocketRoute("/bridge", bridge_socket))
    app.router.routes.append(Mount("/", StaticFiles(directory=static_dir, html=True)))
    return app


def main() -> int:
    config = load_config()
    settings = service_settings(config)
    static_dir = Path(
        os.environ.get("MICRODUCK_STATIC_DIR")
        or SERVICE_ROOT / "web_dist"
    ).resolve()
    if not static_dir.is_dir():
        raise RuntimeError(f"Microduck static bundle is unavailable: {static_dir}")
    run_dir = configured_run_dir()
    listener, port = _open_listener(settings["host"], settings["port"])
    public_url = _replace_url_port(settings["public_url"], port)
    app = create_app(static_dir=static_dir, run_dir=run_dir, public_url=public_url)
    _web_ui_endpoint_artifact(
        run_dir=run_dir,
        proxy_url=_replace_url_port(settings["proxy_url"], port),
        port=port,
    )
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, log_level="info"))
    try:
        server.run(sockets=[listener])
    finally:
        listener.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
