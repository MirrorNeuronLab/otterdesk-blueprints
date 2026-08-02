from __future__ import annotations

from typing import Any


BLUEPRINT_ID = "bibblio_content_studio_coworker"
BUSINESS_GOAL = "Turn Bibblio into a profitable business."
WORKER_ID = "bibblio_content_studio_director"
WORKER_ROLE = "AI Personalized Learning Content Studio Director"
ASPECT_ARTIFACT_ID = "bibblio_content_studio_packet"
ASPECT_PACKET_PATH = "bibblio_content_studio_packet.json"


BLOCKED_ACTIONS = [
    "publish child-facing content",
    "send parent or prospect communications",
    "spend money or launch paid campaigns",
    "change pricing or subscription terms",
    "make learning, medical, or therapeutic outcome claims",
    "change child or family data collection",
]


def as_number(value: Any) -> float | None:
    if value in (None, "") or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round_or_none(value: float | None, digits: int = 4) -> float | None:
    return round(value, digits) if isinstance(value, (int, float)) else None

