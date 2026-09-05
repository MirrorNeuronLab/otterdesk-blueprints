"""In-memory, run-scoped coordination between one browser tab and MCP tools."""

from __future__ import annotations

import asyncio
import copy
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from .protocol import (
    compact_command_progress,
    compact_navigation_result,
    compact_sensor_state,
)


STATE_TTL_SECONDS = 1.0
COMMAND_HISTORY_LIMIT = 100
ACTIVE_STATUSES = frozenset({"queued", "accepted", "running"})
TERMINAL_STATUSES = frozenset({"completed", "rejected", "cancelled"})
SendMessage = Callable[[dict[str, Any]], Awaitable[None]]
ChangeListener = Callable[[dict[str, Any], list[dict[str, Any]]], None]


@dataclass
class Command:
    command_id: str
    kind: str
    payload: dict[str, Any]
    fingerprint: tuple[Any, ...]
    status: str = "queued"
    reason: str = ""
    progress: str = ""
    result: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    def receipt(self) -> dict[str, Any]:
        accepted = self.status in {"queued", "accepted", "running", "completed"}
        receipt = {
            "schema_version": "mn.microduck.command_receipt.v1",
            "command_id": self.command_id,
            "kind": self.kind,
            "status": self.status,
            "state": "failed" if self.status == "rejected" else self.status,
            "ok": accepted,
            "accepted": accepted,
            "reason": self.reason,
            "message": _command_message(
                self.kind, self.status, self.reason, self.progress, self.result
            ),
            "confirmation": _command_confirmation(self.kind, self.payload),
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.progress:
            receipt["progress"] = self.progress
        if self.result:
            receipt["result"] = copy.deepcopy(self.result)
        return receipt


class BridgeHub:
    """Own one browser lease and a bounded command ledger for one service run."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = time.monotonic,
        on_change: ChangeListener | None = None,
    ) -> None:
        self._clock = clock
        self._on_change = on_change
        self._lock = asyncio.Lock()
        self._session_id = ""
        self._send: SendMessage | None = None
        self._last_seen: float | None = None
        self._sensor_state = compact_sensor_state({})
        self._commands: OrderedDict[str, Command] = OrderedDict()
        self._active_command_id = ""
        self._background_command_id = ""
        self._recent_command_id = ""

    async def claim(self, session_id: str, send: SendMessage) -> bool:
        async with self._lock:
            self._expire_if_stale()
            if self._session_id and self._session_id != session_id:
                return False
            self._session_id = session_id
            self._send = send
            self._last_seen = self._clock()
            self._notify()
            return True

    async def disconnect(self, session_id: str) -> None:
        async with self._lock:
            if self._session_id != session_id:
                return
            self._session_id = ""
            self._send = None
            self._last_seen = None
            self._expire_if_stale(force=True)
            self._notify()

    async def update_state(self, session_id: str, raw_state: Any) -> bool:
        async with self._lock:
            if self._session_id != session_id:
                return False
            self._sensor_state = compact_sensor_state(raw_state)
            if self._background_command_id:
                browser_active = self._sensor_state.get("active_command") or {}
                if not (
                    browser_active.get("command_id") == self._background_command_id
                    and browser_active.get("kind") == "free_play"
                    and browser_active.get("status") in ACTIVE_STATUSES
                ):
                    self._background_command_id = ""
            self._last_seen = self._clock()
            self._notify()
            return True

    async def update_command(self, session_id: str, value: Mapping[str, Any]) -> bool:
        async with self._lock:
            if self._session_id != session_id:
                return False
            command_id = str(value.get("command_id") or "")
            command = self._commands.get(command_id)
            status = str(value.get("status") or "")
            if command is None or status not in ACTIVE_STATUSES | TERMINAL_STATUSES:
                return False
            # A stale/disconnected lease is a safety terminal condition. A
            # late browser acknowledgement must not turn that rejection into
            # an apparent successful or operator-cancelled command.
            if command.status in TERMINAL_STATUSES:
                return False
            reason = " ".join(str(value.get("reason") or "").split())[:160]
            progress = compact_command_progress(value.get("progress"))
            result = (
                compact_navigation_result(value.get("result"))
                if command.kind == "find_ball"
                else {}
            )
            if command.kind == "find_ball" and status == "completed" and not _navigation_succeeded(result):
                status = "rejected"
                reason = "invalid_navigation_result"
                result = {}
            command.status = status
            command.reason = reason
            if progress:
                command.progress = progress
            if result and status in TERMINAL_STATUSES:
                command.result = result
            command.updated_at = time.time()
            self._recent_command_id = command_id
            if command.kind == "free_play" and status == "completed":
                self._background_command_id = command_id
            if command_id == self._active_command_id and status in TERMINAL_STATUSES:
                self._active_command_id = ""
            self._last_seen = self._clock()
            self._notify()
            return True

    async def enqueue(
        self,
        *,
        command_id: str,
        kind: str,
        payload: Mapping[str, Any],
    ) -> dict[str, Any]:
        normalized_payload = copy.deepcopy(dict(payload))
        fingerprint = (kind, _freeze(normalized_payload))
        async with self._lock:
            self._expire_if_stale()
            existing = self._commands.get(command_id)
            if existing is not None:
                if existing.fingerprint != fingerprint:
                    return self._rejected_receipt(
                        command_id, kind, "command_id_reused_for_different_effect"
                    )
                return existing.receipt()

            if kind != "stop" and not self._is_ready():
                return self._rejected_receipt(command_id, kind, "browser_not_ready")
            if kind != "stop" and (self._active_command_id or self._background_command_id):
                return self._rejected_receipt(command_id, kind, "browser_busy")

            if kind == "stop" and self._active_command_id:
                active = self._commands.get(self._active_command_id)
                if active is not None and active.status in ACTIVE_STATUSES:
                    active.status = "cancelled"
                    active.reason = "stopped_by_operator"
                    active.updated_at = time.time()
                    self._recent_command_id = active.command_id
                self._active_command_id = ""
            if kind == "stop":
                self._background_command_id = ""

            command = Command(
                command_id=command_id,
                kind=kind,
                payload=normalized_payload,
                fingerprint=fingerprint,
            )
            self._commands[command_id] = command
            self._trim_history()
            self._active_command_id = command_id if kind != "stop" else ""
            sender = self._send
            if sender is None:
                if kind == "stop":
                    command.status = "completed"
                    command.reason = "no_active_browser"
                else:
                    command.status = "rejected"
                    command.reason = "browser_not_ready"
                command.updated_at = time.time()
                self._recent_command_id = command_id
                self._notify()
                return command.receipt()

            self._notify()

        try:
            await sender(
                {
                    "type": "command",
                    "command": {
                        "command_id": command_id,
                        "kind": kind,
                        "payload": normalized_payload,
                    },
                }
            )
        except Exception:
            async with self._lock:
                command.status = "rejected"
                command.reason = "browser_delivery_failed"
                command.updated_at = time.time()
                if self._active_command_id == command_id:
                    self._active_command_id = ""
                self._recent_command_id = command_id
                self._notify()
        return command.receipt()

    async def command_status(self, command_id: str) -> dict[str, Any]:
        async with self._lock:
            self._expire_if_stale()
            command = self._commands.get(command_id)
            if command is None:
                return self._rejected_receipt(command_id, "unknown", "command_not_found")
            return command.receipt()

    async def state(self) -> dict[str, Any]:
        async with self._lock:
            self._expire_if_stale()
            fresh = self._is_fresh()
            active = self._commands.get(self._active_command_id)
            background = self._commands.get(self._background_command_id)
            recent = self._commands.get(self._recent_command_id)
            return {
                "schema_version": "mn.microduck.compact_context.v1",
                "connection": {
                    "connected": fresh,
                    "control_lease": "active" if fresh else "none",
                    "state_age_ms": int(max(self._clock() - self._last_seen, 0) * 1000)
                    if self._last_seen is not None
                    else None,
                },
                "ready": bool(fresh and self._sensor_state.get("ready")),
                "duck": copy.deepcopy(self._sensor_state["duck"]),
                "ball": copy.deepcopy(self._sensor_state["ball"]),
                "active_command": (active or background).receipt() if (active or background) else {},
                "recent_command": recent.receipt() if recent else {},
            }

    def _is_fresh(self) -> bool:
        return bool(self._session_id and self._send and self._last_seen is not None) and (
            self._clock() - self._last_seen <= STATE_TTL_SECONDS
        )

    def _is_ready(self) -> bool:
        return self._is_fresh() and bool(self._sensor_state.get("ready"))

    def _expire_if_stale(self, *, force: bool = False) -> None:
        if not force and self._is_fresh():
            return
        if self._active_command_id:
            command = self._commands.get(self._active_command_id)
            if command is not None and command.status in ACTIVE_STATUSES:
                command.status = "rejected"
                command.reason = "browser_state_stale"
                command.updated_at = time.time()
                self._recent_command_id = command.command_id
                self._schedule_zero(self._send)
            self._active_command_id = ""
        if self._background_command_id:
            self._schedule_zero(self._send)
            self._background_command_id = ""

    @staticmethod
    def _schedule_zero(sender: SendMessage | None) -> None:
        """Best-effort zero command after a stale lease, never a raw action."""

        if sender is None:
            return

        async def send_zero() -> None:
            try:
                await sender(
                    {
                        "type": "command",
                        "command": {
                            "command_id": "system-stop",
                            "kind": "stop",
                            "payload": {},
                        },
                    }
                )
            except Exception:
                # The browser may already have disconnected. Its close handler
                # independently zeroes remote input, so no retry is useful.
                return

        asyncio.create_task(send_zero())

    def _trim_history(self) -> None:
        while len(self._commands) > COMMAND_HISTORY_LIMIT:
            command_id, _ = self._commands.popitem(last=False)
            if command_id == self._recent_command_id:
                self._recent_command_id = ""

    def _rejected_receipt(self, command_id: str, kind: str, reason: str) -> dict[str, Any]:
        return {
            "schema_version": "mn.microduck.command_receipt.v1",
            "command_id": command_id,
            "kind": kind,
            "status": "rejected",
            "state": "failed",
            "ok": False,
            "accepted": False,
            "reason": reason,
            "message": _command_message(kind, "rejected", reason),
            "confirmation": _command_confirmation(kind, {}),
            "created_at": time.time(),
            "updated_at": time.time(),
        }

    def _notify(self) -> None:
        if self._on_change is None:
            return
        state = {
            "session_connected": self._is_fresh(),
            "sensor_state": copy.deepcopy(self._sensor_state),
            "active_command_id": self._active_command_id or self._background_command_id,
        }
        history = [command.receipt() for command in self._commands.values()]
        self._on_change(state, history)


def _freeze(value: Any) -> Any:
    if isinstance(value, Mapping):
        return tuple(sorted((str(key), _freeze(item)) for key, item in value.items()))
    if isinstance(value, list):
        return tuple(_freeze(item) for item in value)
    return value


def _command_confirmation(kind: str, payload: Mapping[str, Any]) -> dict[str, str]:
    if kind == "motion_plan":
        move = payload.get("move") if isinstance(payload.get("move"), Mapping) else {}
        target = str(payload.get("routine") or move.get("direction") or "bounded motion")
        return {"kind": "motion", "label": "MOTION COMMAND", "target": target}
    if kind == "find_ball":
        return {"kind": "navigation", "label": "NAVIGATION COMMAND", "target": "ball"}
    if kind == "free_play":
        return {"kind": "play", "label": "FREE PLAY COMMAND", "target": "ball"}
    if kind == "set_locomotion":
        return {
            "kind": "locomotion",
            "label": "LOCOMOTION COMMAND",
            "target": str(payload.get("locomotion") or "requested mode"),
        }
    if kind == "ball_action":
        return {
            "kind": "ball",
            "label": "BALL COMMAND",
            "target": str(payload.get("action") or "requested action"),
        }
    if kind == "reset":
        return {"kind": "simulation", "label": "RESET COMMAND"}
    if kind == "stop":
        return {"kind": "motion", "label": "STOP COMMAND"}
    return {"kind": "control", "label": "CONTROL COMMAND"}


def _navigation_succeeded(result: Mapping[str, Any]) -> bool:
    distance = result.get("final_distance_m")
    speed = result.get("final_speed_mps")
    duck = result.get("final_duck_position")
    ball = result.get("final_ball_position")
    return bool(
        result.get("outcome") == "found_ball"
        and type(distance) in {int, float}
        and distance <= 0.22
        and type(speed) in {int, float}
        and speed <= 0.05
        and isinstance(duck, Mapping)
        and all(type(duck.get(key)) in {int, float} for key in ("x", "y", "yaw"))
        and isinstance(ball, Mapping)
        and all(type(ball.get(key)) in {int, float} for key in ("x", "y"))
    )


def _command_message(
    kind: str,
    status: str,
    reason: str,
    progress: str = "",
    result: Mapping[str, Any] | None = None,
) -> str:
    if kind == "free_play":
        if status == "completed":
            return "Free play started! I’ll keep finding and kicking the ball until you tell me to stop."
        if status == "running":
            return {
                "turning": "I’m turning toward the ball to keep playing.",
                "approaching": "I’m chasing the ball.",
                "settling": "I reached the ball and I’m getting ready to kick.",
            }.get(progress, "I’m getting ready to play with the ball.")
        if status == "accepted":
            return "I’ll find and kick the ball, then keep playing until you stop me."
        if status == "cancelled":
            return "I stopped free play."
        if status == "rejected":
            return {
                "ball_not_active": "I couldn’t start free play because no ball is active.",
                "kicks_require_legs": "I couldn’t start free play because kicking requires legs.",
                "free_play_unavailable": "I couldn’t start free play because normal walking mode isn’t available.",
                "navigation_timeout": "I couldn’t reach the ball before the navigation time limit.",
                "navigation_travel_limit": "I couldn’t reach the ball before the navigation travel limit.",
                "browser_state_stale": "I stopped free play because the browser state became stale.",
            }.get(reason, f"Free play was rejected: {' '.join(str(reason or 'request rejected').replace('_', ' ').split())}.")
    if kind == "find_ball":
        if status == "completed" and _navigation_succeeded(result or {}):
            return "I found the ball! I’m tired, but I made it."
        if status == "running":
            return {
                "turning": "I’m turning toward the ball.",
                "approaching": "I’m moving toward the ball.",
                "settling": "I reached the ball and I’m stopping.",
            }.get(progress, "I’m looking for the ball.")
        if status == "accepted":
            return "I’ll find the ball."
        if status == "cancelled":
            return "I stopped looking for the ball."
        if status == "rejected":
            return {
                "ball_not_active": "I couldn’t find the ball because no ball is active.",
                "navigation_mode_unavailable": "I couldn’t find the ball because normal walk or drive mode isn’t available.",
                "navigation_timeout": "I stopped looking for the ball after reaching the 30-second limit.",
                "navigation_travel_limit": "I stopped looking for the ball after reaching the 5-meter travel limit.",
                "browser_state_stale": "I stopped looking for the ball because the browser state became stale.",
                "invalid_navigation_result": "I reached the end of navigation, but the browser returned an invalid result.",
            }.get(reason, f"Ball navigation was rejected: {' '.join(str(reason or 'request rejected').replace('_', ' ').split())}.")
    action = {
        "motion_plan": "Motion",
        "set_locomotion": "Locomotion change",
        "ball_action": "Ball action",
        "reset": "Simulation reset",
        "stop": "Stop",
        "find_ball": "Ball navigation",
        "free_play": "Free play",
    }.get(kind, "Command")
    if kind == "stop" and status == "completed":
        return "All actions stopped."
    if status == "rejected":
        detail = " ".join(str(reason or "request rejected").replace("_", " ").split())
        return f"{action} was rejected: {detail}."
    return f"{action} is {status}."
