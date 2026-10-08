"""Scene-level person episodes; no identity or activity inference."""

import math
import re

from .detection_policy import DEFAULT_MONITORING_GOAL


def uses_person_events(goal):
    normalized = re.sub(r"[^a-z0-9 ]", "", " ".join(str(goal).casefold().split()))
    return normalized in {"a person is visible in the video", "a person is visible", "person",
                          "a person is present", "notify me when a person is visible"}


class PersonEpisodes:
    def __init__(self, settings, state=None):
        self.hits_required = int(settings.get("consecutive_hits", 2))
        self.absence_seconds = float(settings.get("absence_seconds", 2))
        self.max_gap_seconds = float(settings.get("max_gap_seconds", 2))
        if not 1 <= self.hits_required <= 10 or not .1 <= self.absence_seconds <= 60 or not .1 <= self.max_gap_seconds <= 60:
            raise ValueError("invalid person episode settings")
        self.state = dict(state or {})

    def update(self, people, timestamp, *, revision=0):
        if not math.isfinite(timestamp):
            raise ValueError("person events require a finite frame timestamp")
        state = self.state
        last = state.get("last_frame_at")
        if last is not None and timestamp <= last:
            return None
        changed = state.get("instruction_revision", revision) != revision
        gap = last is not None and timestamp - last > self.max_gap_seconds
        if changed:
            state.update(active=False, hits=0, absent_since=None)
        elif gap:
            # Missing frames invalidate persistence and cannot establish exit.
            state.update(hits=0, absent_since=None)
        state.update(last_frame_at=timestamp, instruction_revision=revision)
        if people:
            state["absent_since"] = None
            state["hits"] = int(state.get("hits", 0)) + 1
            if state["hits"] == 1:
                state["candidate_started_at"] = timestamp
            if state["hits"] >= self.hits_required and not state.get("active"):
                state.update(active=True, episode=int(state.get("episode", 0)) + 1)
                return {"kind": "person_presence_started", "episode": state["episode"],
                        "started_at": state["candidate_started_at"], "confirmed_at": timestamp,
                        "person_count": len(people), "confidence": max(p["confidence"] for p in people),
                        "boxes": people, "qualification": "sampled_scene_presence_not_identity"}
        else:
            state["hits"] = 0
            if state.get("active"):
                if state.get("absent_since") is None:
                    state["absent_since"] = timestamp
                if timestamp - state["absent_since"] >= self.absence_seconds:
                    state.update(active=False, absent_since=None)
        return None


def person_goal(config, monitoring):
    from .detection_policy import configured_monitoring_goal
    return str(monitoring.get("instruction") or configured_monitoring_goal(config) or DEFAULT_MONITORING_GOAL)
