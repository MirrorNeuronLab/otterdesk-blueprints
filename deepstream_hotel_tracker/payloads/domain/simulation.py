"""Bridge synchronized Isaac Sim render products to RTSP and the live preview."""

import io
import json
import os
import time
from contextlib import ExitStack
from pathlib import Path
from threading import Thread

from PIL import Image

from .deepstream import process
from .layout import CAMERAS, RESOLUTION
from .robot import ROBOT_SAMPLE


SCENE = Path("/opt/hotel/atrium/hotel_reception.usda")
WIDTH, HEIGHT = RESOLUTION
ATLAS_SIZE = (2 * WIDTH, 2 * HEIGHT)
FRAME_BYTES = 3 * ATLAS_SIZE[0] * ATLAS_SIZE[1]
CROPS = tuple(
    (WIDTH * (i % 2), HEIGHT * (i // 2), WIDTH * (i % 2 + 1), HEIGHT * (i // 2 + 1))
    for i in range(len(CAMERAS))
)


class Simulation:
    def __init__(self, work, streams):
        self.streams = streams
        self.calibration_path = work / "isaac_calibration.json"
        self.last_frame = None
        self.preview = None
        self.last_robot = None
        self.failure = None
        read, write = os.pipe()
        try:
            with ExitStack() as startup:
                self.frames = startup.enter_context(os.fdopen(read, "rb"))
                # Isaac's wrapper loads its own Python and graphics libraries.
                # Keep the DeepStream, TensorRT and MN environments in the parent.
                environment = {
                    key: value for key, value in os.environ.items()
                    if key not in {"LD_LIBRARY_PATH", "LD_PRELOAD", "PYTHONPATH", "PYTHONHOME", "BASH_ENV"}
                }
                self.child, self.tail = startup.enter_context(process(
                    ["/isaac-sim/python.sh", "--no-ros-env", "-m", "domain.isaac_scene",
                     str(SCENE), str(self.calibration_path), str(write)],
                    work=Path(__file__).resolve().parent.parent, env=environment, pass_fds=(write,),
                ))
                self.stack = startup.pop_all()
        finally:
            os.close(write)
        self.thread = Thread(target=self._receive, name="hotel-isaac-cameras", daemon=True)
        self.thread.start()

    def _receive(self):
        next_preview = 0.0
        try:
            while header := self.frames.read(ROBOT_SAMPLE.size):
                raw = self.frames.read(FRAME_BYTES)
                if len(header) != ROBOT_SAMPLE.size or len(raw) != FRAME_BYTES:
                    raise RuntimeError("Isaac Sim stopped during a camera frame.")
                frame = Image.frombytes("RGB", ATLAS_SIZE, raw)
                self.streams.send([frame.crop(crop).tobytes() for crop in CROPS])
                now = time.monotonic()
                self.last_frame = now
                x, y, camera = ROBOT_SAMPLE.unpack(header)
                if camera >= 0:
                    self.last_robot = now, (x, y), camera
                if now >= next_preview:
                    with io.BytesIO() as buffer:
                        frame.resize(RESOLUTION, Image.Resampling.BILINEAR).save(buffer, format="JPEG", quality=79)
                        self.preview = buffer.getvalue()
                    next_preview = now + 0.2
        except Exception as error:
            self.failure = error

    def robot_observation(self):
        sample = self.last_robot
        if sample is None:
            return None
        at, position, camera = sample
        if time.monotonic() - at > 1.25:
            return None
        return {"world_xy": [round(value, 3) for value in position], "camera": camera}

    def wait_for_calibration(self, check):
        deadline = time.monotonic() + 600
        while not (self.calibration_path.is_file() and self.last_frame is not None):
            check()
            self.check()
            if time.monotonic() >= deadline:
                raise RuntimeError(f"Isaac Sim did not start the Atrium cameras.\n{self.tail()}")
            time.sleep(.2)
        return json.loads(self.calibration_path.read_text())

    def check(self):
        if self.child.poll() is not None:
            raise RuntimeError(f"Isaac Sim stopped.\n{self.tail()}")
        if self.failure is not None:
            raise RuntimeError("Couldn't receive the live Isaac Sim camera frames.") from self.failure
        if self.last_frame is not None and time.monotonic() - self.last_frame > 20:
            raise RuntimeError("Isaac Sim stopped sending live camera frames.")

    def close(self):
        self.stack.close()
        self.thread.join(timeout=5)
