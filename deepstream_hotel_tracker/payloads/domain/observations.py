"""Consume bounded live observations from the local DeepStream broker."""

import math
import re
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone

from .counting import DoorCounts
from .deepstream import METADATA_TOPIC, MQTT_PORT, SENSORS
from .layout import inside_room


TRACK_ID = re.compile(r"[0-9]{1,20}")
MAX_METADATA_AGE = 15
MAX_TRACK_GAP = 45


def _observation(obj, camera):
    coords = list(obj.bbox3d.coordinates[:3])
    if not TRACK_ID.fullmatch(obj.id) or len(coords) != 3 or not all(map(math.isfinite, coords)):
        return None
    box = [obj.bbox.leftX, obj.bbox.topY, obj.bbox.rightX, obj.bbox.bottomY]
    if not all(map(math.isfinite, box)) or box[0] >= box[2] or box[1] >= box[3]:
        box = None
    return {
        "camera": camera,
        "id": obj.id,
        "world_xyz": [round(value, 4) for value in coords],
        "box_xyxy": [round(value, 2) for value in box] if box else None,
    }


@dataclass
class Visit:
    entered_at: float | None
    last_seen_at: float


class Observations:
    def __init__(self, saved=None):
        self.counts = DoorCounts(saved)
        self.lock = threading.Lock()
        self.first_frame = threading.Event()
        self.last_frame = [None for _ in SENSORS]
        self.last_at = [None for _ in SENSORS]
        self.rows = [() for _ in SENSORS]
        self.visits = {}
        self.updated_at = saved.get("observed_at") if saved else None

    def ingest(self, payload, *, now=None, timestamp=None):
        from .nvidia_mv3dt_schema_pb2 import Frame

        if not payload or len(payload) > 128 * 1024:
            raise ValueError("Invalid DeepStream metadata size.")
        frame = Frame.FromString(payload)
        frame_number = int(frame.id)
        if frame.sensorId not in SENSORS:
            raise ValueError("DeepStream metadata is missing a configured hotel camera ID.")
        camera = SENSORS.index(frame.sensorId)
        if not 0 <= frame_number < 2**64:
            raise ValueError("DeepStream emitted an invalid frame number.")
        if len(frame.objects) > 200:
            raise ValueError("DeepStream emitted too many tracked objects in one camera frame.")
        now = time.monotonic() if now is None else now
        stamp = timestamp or datetime.now(timezone.utc).isoformat(timespec="milliseconds")
        with self.lock:
            previous = self.last_frame[camera]
            if previous is not None and frame_number <= previous:
                return
            rows = {}
            for obj in frame.objects:
                observation = _observation(obj, camera)
                if observation:
                    rows[obj.id] = observation
            self.last_frame[camera] = frame_number
            self.last_at[camera] = now
            self.rows[camera] = tuple(rows.values())
            crossings = self.counts.observe(camera, self.rows[camera], now, stamp)
            self._update_visits(rows, crossings, now)
            self.updated_at = stamp
            self.first_frame.set()

    def _update_visits(self, rows, crossings, now):
        self.visits = {
            track: visit
            for track, visit in self.visits.items()
            if now - visit.last_seen_at <= MAX_TRACK_GAP
        }
        for track, row in rows.items():
            x, y, _ = row["world_xyz"]
            direction = crossings.get(track)
            visit = self.visits.get(track)
            if direction == "left":
                self.visits[track] = Visit(None, now)
            elif direction == "entered" or (visit is None and inside_room(x, y)):
                if visit is None or visit.entered_at is None:
                    self.visits[track] = Visit(now, now)
                else:
                    visit.last_seen_at = now
            elif visit is not None:
                visit.last_seen_at = now

    def require_recent(self):
        with self.lock:
            latest = max((value for value in self.last_at if value is not None), default=None)
        if latest is not None and time.monotonic() - latest > MAX_METADATA_AGE:
            raise RuntimeError("NVIDIA DeepStream stopped sending hotel observations.")

    def snapshot(self):
        with self.lock:
            return {**self.counts.snapshot(), "observed_at": self.updated_at}

    def visible(self, *, now=None):
        with self.lock:
            now = time.monotonic() if now is None else now
            return [
                {**row, "dwell_seconds": self._dwell(row["id"], now)}
                for at, view in zip(self.last_at, self.rows)
                if at is not None and now - at <= 1.5
                for row in view
            ]

    def _dwell(self, track, now):
        visit = self.visits.get(track)
        if visit is None or visit.entered_at is None:
            return None
        return int(max(0, now - visit.entered_at))


@contextmanager
def collect(observations, broker, check):
    from paho.mqtt import client as mqtt

    client = mqtt.Client(protocol=mqtt.MQTTv311)
    ready = threading.Event()
    errors = []

    def on_connect(connection, _data, _flags, result):
        if result != 0 or connection.subscribe(METADATA_TOPIC)[0] != mqtt.MQTT_ERR_SUCCESS:
            errors.append("The DeepStream metadata subscription failed.")
            ready.set()

    def on_subscribe(_connection, _data, _identifier, granted_qos):
        if granted_qos != [0] and tuple(granted_qos) != (0,):
            errors.append("The DeepStream metadata subscription was rejected.")
        ready.set()

    def on_disconnect(_connection, _data, result):
        if result:
            errors.append("The DeepStream metadata broker disconnected.")

    def on_message(_connection, _data, message):
        if not errors:
            try:
                observations.ingest(message.payload)
            except (ValueError, IndexError, TypeError) as error:
                errors.append(str(error))
            except Exception as error:
                errors.append(f"DeepStream emitted unreadable metadata ({type(error).__name__}).")

    client.on_connect = on_connect
    client.on_subscribe = on_subscribe
    client.on_disconnect = on_disconnect
    client.on_message = on_message
    deadline = time.monotonic() + 10
    while True:
        check()
        try:
            client.connect("127.0.0.1", MQTT_PORT, keepalive=30)
            break
        except ConnectionRefusedError as error:
            if broker.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Couldn't start the DeepStream metadata broker.") from error
            time.sleep(0.1)

    client.loop_start()

    def require_subscription():
        if errors:
            raise RuntimeError(errors[0])

    try:
        if not ready.wait(timeout=5) or errors:
            raise RuntimeError("Couldn't subscribe to the DeepStream metadata broker.")
        yield require_subscription
    finally:
        client.disconnect()
        client.loop_stop()
