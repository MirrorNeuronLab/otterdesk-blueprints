"""Count confirmed traversals of the hotel's calibrated door thresholds."""

import math
from collections import deque
from dataclasses import dataclass

from .layout import DOORS


SCHEMA = "mn.deepstream_hotel.people_counts.v1"
COUNTS_PATH = "people_counts.json"
RECENT_LIMIT = 16
DEADBAND = 0.28
MAX_GAP = 2.8
MAX_TRAVEL = 2.5
DOORS_BY_CAMERA = {door.camera: door for door in DOORS}


@dataclass(frozen=True)
class Position:
    x: float
    y: float
    at: float


class DoorCounts:
    def __init__(self, saved=None):
        self.doors = {door.id: {"entered": 0, "left": 0} for door in DOORS}
        self.recent = deque(maxlen=RECENT_LIMIT)
        self.previous = {}
        if saved is not None:
            if saved["schema_version"] != SCHEMA or set(saved["doors"]) != set(self.doors):
                raise ValueError("Saved hotel counts do not match the live door configuration.")
            for key, totals in self.doors.items():
                for direction in totals:
                    value = saved["doors"][key][direction]
                    if type(value) is not int or value < 0:
                        raise ValueError("Saved hotel counts are invalid.")
                    totals[direction] = value
            self.recent.extend(saved["recent_crossings"][:RECENT_LIMIT])

    def observe(self, camera, rows, now, timestamp):
        self.previous = {
            key: point for key, point in self.previous.items() if now - point.at <= MAX_GAP
        }
        # Observe each threshold from a single unobstructed camera. Other
        # views still contribute to DeepStream's multi-view association.
        door = DOORS_BY_CAMERA.get(camera)
        crossings = {}
        if door is None:
            return crossings
        for row in rows:
            x, y, _ = row["world_xyz"]
            inside = door.inside_distance(y)
            if abs(inside) < DEADBAND:
                continue
            key = camera, row["id"]
            before = self.previous.get(key)
            self.previous[key] = Position(x, y, now)
            if before is None or (inside > 0) == (door.inside_distance(before.y) > 0):
                continue
            if math.hypot(x - before.x, y - before.y) > MAX_TRAVEL:
                continue
            crossing_x = before.x + (x - before.x) * (door.y - before.y) / (y - before.y)
            if abs(crossing_x - door.x) <= door.half_width:
                direction = "entered" if inside > 0 else "left"
                crossings[row["id"]] = direction
                self.doors[door.id][direction] += 1
                self.recent.appendleft({
                    "door": door.id, "direction": direction, "observed_at": timestamp,
                })
        return crossings

    def snapshot(self):
        return {
            "schema_version": SCHEMA,
            "entered": sum(totals["entered"] for totals in self.doors.values()),
            "left": sum(totals["left"] for totals in self.doors.values()),
            "doors": {door: dict(totals) for door, totals in self.doors.items()},
            "recent_crossings": list(self.recent),
        }
