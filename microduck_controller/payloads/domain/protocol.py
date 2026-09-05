"""Small, strict wire contracts shared by the MCP and browser bridge surfaces."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID


MOTION_DIRECTIONS = frozenset({"forward", "backward", "turn_left", "turn_right"})
LOCOMOTION_MODES = frozenset({"legs", "rollers"})
BALL_ACTIONS = frozenset({"spawn_ball", "kick_left", "kick_right"})
NAVIGATION_PROGRESS = frozenset({"turning", "approaching", "settling"})
NAVIGATION_OUTCOMES = frozenset(
    {
        "found_ball",
        "ball_not_active",
        "navigation_mode_unavailable",
        "timeout",
        "travel_exhausted",
        "cancelled",
    }
)
MAX_SEGMENTS = 8
MIN_SEGMENT_MS = 100
MAX_SEGMENT_MS = 1_000
MAX_PLAN_MS = 5_000


class ProtocolError(ValueError):
    """Raised when an MCP or bridge payload violates the public contract."""


def validate_command_id(value: Any) -> str:
    """Return a canonical UUID string used to make effects safely retryable."""

    try:
        return str(UUID(str(value)))
    except (TypeError, ValueError, AttributeError) as error:
        raise ProtocolError("command_id must be a UUID") from error


def validate_motion_plan(value: Any) -> list[dict[str, Any]]:
    """Validate a bounded, high-level movement plan with no raw velocities."""

    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise ProtocolError("segments must be a list")
    if not 1 <= len(value) <= MAX_SEGMENTS:
        raise ProtocolError(f"segments must contain between 1 and {MAX_SEGMENTS} items")

    total_duration = 0
    normalized: list[dict[str, Any]] = []
    for index, segment in enumerate(value):
        if not isinstance(segment, Mapping):
            raise ProtocolError(f"segments[{index}] must be an object")
        if set(segment) != {"direction", "duration_ms"}:
            raise ProtocolError(
                f"segments[{index}] must contain exactly direction and duration_ms"
            )
        direction = segment.get("direction")
        if direction not in MOTION_DIRECTIONS:
            raise ProtocolError(
                "segments[%d].direction must be one of %s"
                % (index, ", ".join(sorted(MOTION_DIRECTIONS)))
            )
        duration_ms = segment.get("duration_ms")
        if type(duration_ms) is not int or not MIN_SEGMENT_MS <= duration_ms <= MAX_SEGMENT_MS:
            raise ProtocolError(
                f"segments[{index}].duration_ms must be an integer from "
                f"{MIN_SEGMENT_MS} to {MAX_SEGMENT_MS}"
            )
        total_duration += duration_ms
        normalized.append({"direction": direction, "duration_ms": duration_ms})

    if total_duration > MAX_PLAN_MS:
        raise ProtocolError(f"motion-plan duration must not exceed {MAX_PLAN_MS} ms")
    return normalized


def validate_locomotion(value: Any) -> str:
    if value not in LOCOMOTION_MODES:
        raise ProtocolError("locomotion must be either legs or rollers")
    return str(value)


def validate_ball_action(value: Any) -> str:
    if value not in BALL_ACTIONS:
        raise ProtocolError(
            "action must be one of " + ", ".join(sorted(BALL_ACTIONS))
        )
    return str(value)


def compact_sensor_state(value: Any) -> dict[str, Any]:
    """Keep only bounded, simulation-safe state supplied by the browser tab."""

    raw = value if isinstance(value, Mapping) else {}
    duck = raw.get("duck") if isinstance(raw.get("duck"), Mapping) else {}
    ball = raw.get("ball") if isinstance(raw.get("ball"), Mapping) else {}
    active_command = (
        raw.get("active_command")
        if isinstance(raw.get("active_command"), Mapping)
        else {}
    )
    recent_command = (
        raw.get("recent_command")
        if isinstance(raw.get("recent_command"), Mapping)
        else {}
    )
    return {
        "schema_version": "mn.microduck.sensor_state.v1",
        "ready": bool(raw.get("ready")),
        "duck": {
            "x": _number(duck.get("x")),
            "y": _number(duck.get("y")),
            "yaw": _number(duck.get("yaw")),
            "speed": _number(duck.get("speed")),
            "mode": _text(duck.get("mode"), limit=32),
            "locomotion": _text(duck.get("locomotion"), limit=16),
        },
        "ball": {
            "active": bool(ball.get("active")),
            "x": _number(ball.get("x")),
            "y": _number(ball.get("y")),
            "distance": _number(ball.get("distance")),
        },
        "active_command": _command_summary(active_command),
        "recent_command": _command_summary(recent_command),
    }


def compact_command_progress(value: Any) -> str:
    """Allow only the three documented navigation phase names."""

    return str(value) if value in NAVIGATION_PROGRESS else ""


def compact_navigation_result(value: Any) -> dict[str, Any]:
    """Validate and bound the untrusted browser's navigation metrics."""

    if not isinstance(value, Mapping):
        return {}
    if value.get("schema_version") != "mn.microduck.navigation_result.v1":
        return {}
    outcome = value.get("outcome")
    locomotion = value.get("locomotion")
    if outcome not in NAVIGATION_OUTCOMES or locomotion not in LOCOMOTION_MODES:
        return {}

    elapsed_ms = _bounded_int(value.get("elapsed_ms"), minimum=0, maximum=60_000)
    path_length_m = _bounded_number(value.get("path_length_m"), minimum=0, maximum=100)
    forward_ticks = _bounded_int(value.get("forward_ticks"), minimum=0, maximum=1_000_000)
    turn_ticks = _bounded_int(value.get("turn_ticks"), minimum=0, maximum=1_000_000)
    corrections = _bounded_int(value.get("corrections"), minimum=0, maximum=1_000_000)
    final_distance_m = _bounded_number(
        value.get("final_distance_m"), minimum=0, maximum=200, nullable=True
    )
    final_speed_mps = _bounded_number(
        value.get("final_speed_mps"), minimum=0, maximum=100, nullable=True
    )
    duck_position = _compact_position(value.get("final_duck_position"), include_yaw=True)
    ball_position = _compact_position(value.get("final_ball_position"), include_yaw=False)
    required = (
        elapsed_ms,
        path_length_m,
        forward_ticks,
        turn_ticks,
        corrections,
        duck_position,
        ball_position,
    )
    if any(item is None for item in required):
        return {}
    return {
        "schema_version": "mn.microduck.navigation_result.v1",
        "outcome": str(outcome),
        "elapsed_ms": elapsed_ms,
        "path_length_m": path_length_m,
        "forward_ticks": forward_ticks,
        "turn_ticks": turn_ticks,
        "corrections": corrections,
        "final_distance_m": final_distance_m,
        "final_duck_position": duck_position,
        "final_ball_position": ball_position,
        "final_speed_mps": final_speed_mps,
        "locomotion": str(locomotion),
    }


def _command_summary(value: Mapping[str, Any]) -> dict[str, str]:
    return {
        "command_id": _text(value.get("command_id"), limit=64),
        "kind": _text(value.get("kind"), limit=32),
        "status": _text(value.get("status"), limit=32),
        "reason": _text(value.get("reason"), limit=160),
    }


def _number(value: Any) -> float | None:
    if type(value) not in {int, float}:
        return None
    if not math.isfinite(float(value)):
        return None
    return round(float(value), 4)


def _bounded_number(
    value: Any,
    *,
    minimum: float,
    maximum: float,
    nullable: bool = False,
) -> float | None:
    if value is None and nullable:
        return None
    number = _number(value)
    if number is None or not minimum <= number <= maximum:
        return None
    return number


def _bounded_int(value: Any, *, minimum: int, maximum: int) -> int | None:
    if type(value) is not int or not minimum <= value <= maximum:
        return None
    return value


def _compact_position(value: Any, *, include_yaw: bool) -> dict[str, float | None] | None:
    if not isinstance(value, Mapping):
        return None
    keys = ("x", "y", "yaw") if include_yaw else ("x", "y")
    result: dict[str, float | None] = {}
    for key in keys:
        number = _bounded_number(value.get(key), minimum=-100, maximum=100, nullable=True)
        if value.get(key) is not None and number is None:
            return None
        result[key] = number
    return result


def _text(value: Any, *, limit: int) -> str:
    return " ".join(str(value or "").split())[:limit]
