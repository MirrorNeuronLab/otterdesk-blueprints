"""Supervise live simulation, DeepStream tracking and the counts workspace."""

import json
import time
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory

from mn_sdk.blueprint.hooks import report_activity
from mn_sdk.blueprint.services import claim_service_web_ui
from mn_sdk_common.beacon import mark_agent_progress
from mn_sdk_common.files import atomic_write_json
from mn_sdk_web_ui import resolve_web_ui_binding

from .counting import COUNTS_PATH
from .deepstream import detector_ready, prepare, prepare_detector, process, require_gpu, start_pipeline
from .observations import Observations, collect
from .simulation import SCENE, Simulation
from .streams import CameraStreams
from .workspace import Workspace, advertised_url


def check_lobby_setup(_block, _inputs):
    require_gpu()
    if not SCENE.is_file():
        raise RuntimeError("The hotel lobby scene is missing.")
    return {}


def prepare_guest_detection(block, _inputs):
    with TemporaryDirectory(prefix="hotel-detector-") as work:
        prepare_detector(Path(work), block.check)
    return {}


class Hotel:
    def __init__(self, block):
        self.block = block
        self.stack = ExitStack()
        self.phase = "starting"
        path = block.store.path(COUNTS_PATH)
        saved = json.loads(path.read_text()) if path.exists() else None
        self.observations = Observations(saved)
        self.last_report = None
        self.last_observation = None
        self.count_locations = dict.fromkeys((path, block.output_directory / COUNTS_PATH))

    def snapshot(self):
        return {"status": self.phase, **self.observations.snapshot()}

    def publish(self, snapshot):
        # The Docker worker and the host's run reader may have different UIDs.
        for location in self.count_locations:
            atomic_write_json(location, snapshot, mode=0o644)

    def start(self):
        require_gpu()
        work = Path(self.stack.enter_context(TemporaryDirectory(prefix="hotel-live-")))
        if not detector_ready():
            report_activity("Preparing guest detection", kind="action")
        prepare_detector(work, self.block.check)
        report_activity("Starting the lobby simulation", kind="action")
        streams = CameraStreams()
        self.stack.callback(streams.close)
        self.simulation = Simulation(work, streams)
        self.stack.callback(self.simulation.close)
        binding = resolve_web_ui_binding(self.block.config, environment=self.block.environment)
        workspace = Workspace(
            binding.host, binding.port,
            lambda: {
                **self.snapshot(),
                "tracks": self.observations.visible(),
                "robot": self.simulation.robot_observation(),
            },
            lambda: self.simulation.preview,
        )
        self.stack.callback(workspace.close)
        claim_service_web_ui(
            self.block, title="Hotel lobby live",
            url=advertised_url(binding, workspace.port, self.block.environment),
            service_name="hotel-lobby-live", node_id=self.block.agent_id,
            http_ports=[workspace.port],
        )
        self.publish(self.snapshot())
        calibrations = self.simulation.wait_for_calibration(self.block.check)
        report_activity("Checking live cameras and guest tracking", kind="action")
        prepare(work, streams.feeds, calibrations)
        broker, _tail = self.stack.enter_context(process(["mosquitto", "-c", "mosquitto.conf"], work=work))
        self.check_subscription = self.stack.enter_context(collect(self.observations, broker, self.block.check))
        self.pipeline, self.pipeline_tail = self.stack.enter_context(start_pipeline(work))
        self.pipeline_started = time.monotonic()

    def check(self):
        try:
            self.simulation.check()
            self.check_subscription()
            if self.pipeline.poll() is not None:
                raise RuntimeError(f"NVIDIA DeepStream stopped.\n{self.pipeline_tail()}")
            if not self.observations.first_frame.is_set() and time.monotonic() - self.pipeline_started > 60:
                raise RuntimeError(f"DeepStream did not report live hotel observations.\n{self.pipeline_tail()}")
            self.observations.require_recent()
        except Exception:
            self.phase = "failed"
            raise

    def close(self):
        try:
            self.stack.close()
        finally:
            if self.phase != "failed":
                self.phase = "stopped"
            self.publish(self.snapshot())


def start(block, _inputs):
    hotel = Hotel(block)
    block.resources["hotel"] = hotel
    try:
        hotel.start()
    except Exception as error:
        if getattr(error, "code", None) != "cancelled":
            hotel.phase = "failed"
        raise


def ready(block, _inputs):
    hotel = block.resources["hotel"]
    hotel.check()
    if hotel.observations.first_frame.is_set() and hotel.simulation.preview is not None:
        if hotel.phase != "running":
            hotel.phase = "running"
            report_activity("The lobby is live. Tracking guests and counting arrivals and departures.", kind="result")
        return True
    return False


def health(block, _inputs):
    block.resources["hotel"].check()
    return True


def cycle(block, _inputs):
    hotel = block.resources["hotel"]
    snapshot = hotel.snapshot()
    hotel.publish(snapshot)
    if snapshot["observed_at"] != hotel.last_observation:
        mark_agent_progress()
        hotel.last_observation = snapshot["observed_at"]
    totals = (snapshot["entered"], snapshot["left"])
    if totals != hotel.last_report:
        if hotel.last_report is not None:
            report_activity(f"Observed {totals[0]} entries and {totals[1]} departures at the hotel doors.", kind="finding")
        hotel.last_report = totals
    return {"entered": totals[0], "left": totals[1]}


def stop(block, _inputs):
    hotel = block.resources.pop("hotel", None)
    if hotel:
        hotel.close()
