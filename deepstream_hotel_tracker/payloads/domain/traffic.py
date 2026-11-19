"""Continuously generate new guest trips through the 3D lobby."""

import math
import random
from dataclasses import dataclass

from .layout import DESK, ENTRANCE, EXITS, Door


MAX_GUESTS = 4
MIN_RECEPTION_SECONDS = 30.0
QUEUE_X = 0.0
QUEUE_FRONT_Y = DESK[1] - 1.25
QUEUE_SPACING = 1.55
QUEUE_ENTRY_Y = QUEUE_FRONT_Y - QUEUE_SPACING * MAX_GUESTS
WALK_CYCLE_SECONDS = 0.8


@dataclass
class Guest:
    id: int
    slot: int
    x: float
    y: float
    route: list[tuple[float, float]]
    speed: float
    exit_door: Door
    reception_seconds: float
    phase: str = "arriving"
    queued_at: float | None = None
    depart_at: float | None = None
    heading: float = 0
    walk_time: float = 0
    walking: bool = False

    def advance(self, seconds):
        distance = self.speed * seconds
        self.walking = False
        while self.route and distance > 0:
            x, y = self.route[0]
            dx, dy = x - self.x, y - self.y
            remaining = math.hypot(dx, dy)
            if not remaining:
                self.route.pop(0)
                continue
            self.heading = math.degrees(math.atan2(-dx, dy))
            traveled = min(remaining, distance)
            self.walking = True
            self.walk_time = (self.walk_time + traveled / 1.3) % WALK_CYCLE_SECONDS
            distance -= traveled
            if traveled == remaining:
                self.x, self.y = self.route.pop(0)
            else:
                self.x += dx * traveled / remaining
                self.y += dy * traveled / remaining


class Lobby:
    def __init__(self, seed=None):
        self.random = random.Random(seed)
        self.guests = []
        self.next_guest = 0
        self.arrival_in = 0.0
        self.elapsed = 0.0

    def _arrival(self):
        rng = self.random
        exit_door = EXITS[self.next_guest % len(EXITS)]
        side = -1 if exit_door.x < 0 else 1
        entrance_x = ENTRANCE.x + side * rng.uniform(0.55, 0.95)
        occupied = {guest.slot for guest in self.guests}
        slot = next(i for i in range(MAX_GUESTS) if i not in occupied)
        self.guests.append(Guest(
            id=self.next_guest, slot=slot, x=entrance_x, y=ENTRANCE.y - 4.2,
            route=[(entrance_x, ENTRANCE.y + 2.4), (QUEUE_X, QUEUE_ENTRY_Y)],
            speed=rng.uniform(1.2, 1.45), exit_door=exit_door,
            reception_seconds=rng.uniform(MIN_RECEPTION_SECONDS, 42.0),
        ))
        self.next_guest += 1
        self.arrival_in = rng.uniform(7.0, 20.0)

    def _depart(self, guest):
        door = guest.exit_door
        side = -1 if door.x < 0 else 1
        exit_x = door.x + self.random.uniform(-0.35, 0.35)
        guest.phase = "departing"
        guest.route = [
            (side * 3.8, QUEUE_FRONT_Y),
            (side * 5.35, QUEUE_FRONT_Y + 0.65),
            (exit_x, door.y - 2.1),
            (exit_x, door.y + 2.5),
        ]

    def _advance_queue(self, queue, seconds):
        if not queue:
            return
        target_y = QUEUE_FRONT_Y
        for guest in queue:
            guest.route = [(QUEUE_X, max(guest.y, target_y))]
            guest.advance(seconds)
            if not guest.route and guest.queued_at is None:
                guest.queued_at = self.elapsed
            target_y = guest.y - QUEUE_SPACING

        head = queue[0]
        if head.route:
            return
        if head.depart_at is None:
            head.depart_at = max(
                head.queued_at + head.reception_seconds,
                self.elapsed + self.random.uniform(7.0, 13.0),
            )
        if self.elapsed >= head.depart_at:
            self._depart(head)

    def advance(self, seconds):
        self.elapsed += seconds
        self.arrival_in -= seconds
        if self.arrival_in <= 0 and len(self.guests) < MAX_GUESTS:
            self._arrival()
        queue = []
        for guest in self.guests:
            if guest.phase == "queued":
                queue.append(guest)
                continue
            guest.advance(seconds)
            if guest.phase == "arriving" and not guest.route:
                guest.phase = "queued"
                guest.heading = 0
        self._advance_queue(queue, seconds)
        self.guests = [guest for guest in self.guests if guest.phase != "departing" or guest.route]
        return self.guests
