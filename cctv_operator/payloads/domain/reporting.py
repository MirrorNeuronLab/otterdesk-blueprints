from __future__ import annotations

from typing import Any, Mapping


SAMPLING_EVENT_TYPES = {
    "cctv_operator_scene_change_detected",
    "cctv_operator_burst_started",
    "cctv_operator_burst_completed",
    "cctv_operator_frame_batch_ready",
    "cctv_operator_sample_skipped",
    "cctv_operator_queue_lag",
}


def sampling_records(events: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "type": str(event.get("type")),
            **dict(event.get("payload") or {}),
        }
        for event in events
        if isinstance(event, Mapping)
        and event.get("type") in SAMPLING_EVENT_TYPES
        and isinstance(event.get("payload"), Mapping)
    ]


def bounded_history(previous: Any, current: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    history = previous if isinstance(previous, list) else []
    return [*history, *current][-limit:]
