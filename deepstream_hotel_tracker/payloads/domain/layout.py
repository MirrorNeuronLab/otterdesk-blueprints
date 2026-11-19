"""Camera order and door geometry for the bundled OpenUSD Atrium stage."""

from dataclasses import dataclass


WIDTH, DEPTH = 20, 16
RESOLUTION = (960, 540)
FPS = 10
CAMERAS = tuple(f"/World/Cameras/Hotel_Reception_Cam{i:03d}" for i in range(1, 5))
DESK = (-4.1, 5.0, 4.1, 6.5)
RUGS = ((-9.4, -4.1, -6.2, 4.1), (6.2, -4.1, 9.4, 4.1))


@dataclass(frozen=True)
class Door:
    id: str
    label: str
    x: float
    y: float
    half_width: float
    camera: int

    def inside_distance(self, y):
        return y - self.y if self.y < 0 else self.y - y


DOORS = (
    Door("west_exit", "West exit", -6.6, DEPTH / 2, 1.13, 0),
    Door("entrance", "Main entrance", 0, -DEPTH / 2, 1.9, 2),
    Door("east_exit", "East exit", 6.6, DEPTH / 2, 1.13, 1),
)
ENTRANCE = DOORS[1]
EXITS = (DOORS[0], DOORS[2])


def inside_room(x, y):
    return abs(x) <= WIDTH / 2 and abs(y) <= DEPTH / 2


def floor_plan():
    return {
        "size": [WIDTH, DEPTH],
        "desk": DESK,
        "rugs": RUGS,
        "doors": [
            {"id": door.id, "label": door.label, "x": door.x, "y": door.y, "width": 2 * door.half_width}
            for door in DOORS
        ],
    }
