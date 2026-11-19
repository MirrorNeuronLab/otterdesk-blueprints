import configparser
import json
import math
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from jsonschema import Draft202012Validator

from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk_common.committed_artifacts import CommittedJsonStore


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def payload(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))


def test_catalog_compiles_ordered_startup_before_live_monitoring():
    package = read_blueprint(ROOT)
    compiled = compile_blueprint(package).manifest
    assert compiled["type"] == "service"
    assert compiled["service"]["run_until"] == "manual_stop"
    assert compiled["service"]["state_artifact"] == "people_counts.json"
    assert compiled["requirements"]["gpu"] == {
        "driver": "cuda", "vendor": "nvidia", "enforcement": "hard",
        "memory_operator": ">=", "min_count": 1, "min_memory_mb": 49152,
    }
    workers = [node["config"] for node in compiled["agents"]["nodes"] if node["config"].get("dockerfile")]
    assert len(workers) == 3
    assert len({worker["image"] for worker in workers}) == 1
    for worker in workers:
        assert worker["dockerfile"] == "docker_worker/Dockerfile"
        assert worker["gpus"] == "all"
        assert worker["command"] == ["/opt/mn-venv/bin/python3", "-m", "mn_sdk.step_runtime"]
    workflow = compiled["workflow"]
    assert [(step["id"], step["needs"]) for step in workflow["steps"]] == [
        ("check_lobby_setup", []),
        ("prepare_guest_detection", ["check_lobby_setup"]),
        ("monitor_live_lobby", ["prepare_guest_detection"]),
    ]
    assert workflow["service_lifecycle"]["phases"] == {
        "check_lobby_setup": "startup",
        "prepare_guest_detection": "startup",
        "monitor_live_lobby": "service",
    }
    assert compiled["metadata"]["web_ui"]["adapter"] == "external-url"
    asset_paths = {asset.path for asset in package.assets}
    assert {
        "payloads/isaac/assets/hotel_reception.usda",
        "payloads/isaac/assets/hotel_sign.png",
        "payloads/isaac/assets/exit_sign.png",
        "payloads/isaac/assets/downloads/guest_walk.usdc",
        "payloads/isaac/assets/vendor_assets.json",
        "payloads/isaac/assets/agibot.usda",
        "payloads/isaac/assets/agibot_assets.json",
        "payloads/domain/web_assets/floor-plan.js",
    } <= asset_paths


def test_live_pipeline_configs_use_four_rtsp_sources_and_their_calibration(tmp_path):
    import yaml

    from domain.deepstream import prepare
    from domain.layout import CAMERAS

    feeds = [f"rtsp://127.0.0.1:8554/camera-{i}" for i in range(1, 5)]
    models = [
        {"projectionMatrix_3x4_w2p": [float(i + j) for j in range(12)], "worldUnitsPerMeter": 1.0}
        for i in range(len(CAMERAS))
    ]
    prepare(tmp_path, feeds, models)
    config = configparser.ConfigParser()
    config.read(tmp_path / "deepstream.ini")
    assert config.getint("streammux", "batch-size") == 4
    assert config.getboolean("streammux", "live-source")
    assert config["sink1"]["msg-broker-conn-str"] == "127.0.0.1;1883"
    for i, feed in enumerate(feeds):
        assert config[f"source{i}"]["uri"] == feed
        assert config.getint(f"source{i}", "type") == 4
        assert yaml.safe_load((tmp_path / f"camera-{i}.yml").read_text()) == models[i]
    tracker = (tmp_path / "tracker.yml").read_text()
    assert tracker.count("camera-") == 4
    assert "multiViewAssociatorType: 1" in tracker


def test_detector_preparation_rebuilds_an_unverified_engine_and_reuses_a_ready_one(tmp_path):
    from domain import deepstream

    engine = tmp_path / "detector.engine"
    engine.write_bytes(b"incomplete engine")

    with patch.object(deepstream, "ENGINE", engine), patch.object(deepstream, "_nvidia_process") as process:
        child = SimpleNamespace(poll=lambda: 0, returncode=0)
        process.return_value.__enter__.return_value = (child, lambda: "")

        def build(*_args):
            assert not engine.exists()
            engine.write_bytes(b"prepared engine")
            return process.return_value

        process.side_effect = build
        deepstream.prepare_detector(tmp_path, Mock())
        assert deepstream.detector_ready()
        assert engine.read_bytes() == b"prepared engine"
        deepstream.prepare_detector(tmp_path, Mock())
        process.assert_called_once()


def test_bundled_usd_dependencies_include_transitive_mdl_imports():
    lock = ROOT / "payloads/isaac/assets/vendor_assets.json"
    assets = json.loads(lock.read_text())
    shaders = [Path(name) for name in assets if Path(name).name == "OmniPBR.mdl"]
    assert shaders
    for shader in shaders:
        assert shader.with_name("OmniPBRBase.mdl").as_posix() in assets
        assert shader.with_name("OmniPBR_ClearCoat.mdl").as_posix() in assets


def test_openusd_exits_match_calibrated_thresholds():
    pytest.importorskip("numpy")
    Usd = pytest.importorskip("pxr.Usd")
    from pxr import UsdGeom

    from domain.isaac_scene import camera_calibration
    from domain.layout import CAMERAS, DOORS, ENTRANCE, EXITS, RESOLUTION

    stage_path = ROOT / "payloads/isaac/assets/hotel_reception.usda"
    mask = Usd.StagePopulationMask([
        "/World/Cameras", "/World/Architecture", "/World/ReceptionExits", "/World/Entrance/Mat9",
    ])
    stage = Usd.Stage.OpenMasked(str(stage_path), mask)
    assert UsdGeom.GetStageMetersPerUnit(stage) == 1
    assert UsdGeom.GetStageUpAxis(stage) == UsdGeom.Tokens.z
    for door, side in zip(EXITS, ("West", "East")):
        threshold = stage.GetPrimAtPath(f"/World/ReceptionExits/{side}Exit/Threshold")
        assert tuple(threshold.GetAttribute("xformOp:translate").Get())[:2] == (door.x, door.y)
        assert door.y == -ENTRANCE.y
        for panel in ("West", "Center", "East"):
            wall = stage.GetPrimAtPath(f"/World/Architecture/NorthWall{panel}")
            center = wall.GetAttribute("xformOp:translate").Get()[0]
            half_width = wall.GetAttribute("xformOp:scale").Get()[0] / 2
            assert abs(center - door.x) > half_width + door.half_width

    width, height = RESOLUTION
    for door in DOORS:
        camera = UsdGeom.Camera.Get(stage, CAMERAS[door.camera])
        matrix = camera_calibration(camera)["projectionMatrix_3x4_w2p"]
        for y in (door.y - .8, door.y + .8):
            for x in (door.x - .45, door.x + .45):
                for z in (0, 1.7):
                    point = [x, y, z, 1]
                    u, v, w = (sum(a * b for a, b in zip(matrix[i:i+4], point)) for i in (0, 4, 8))
                    assert w > 0
                    assert 0 < u / w < width and 0 < v / w < height


def test_guests_queue_in_order_for_at_least_thirty_seconds_and_use_both_exits():
    from domain.layout import DOORS, ENTRANCE, EXITS
    from domain.traffic import Lobby, MAX_GUESTS, MIN_RECEPTION_SECONDS, QUEUE_SPACING, QUEUE_X

    lobby = Lobby(seed=35)
    previous = {}
    crossings = []
    joined = {}
    departed = []
    queue_lengths = set()
    for tick in range(5500):
        guests = lobby.advance(.1)
        assert len(guests) <= MAX_GUESTS
        assert len({guest.slot for guest in guests}) == len(guests)
        queue = [guest for guest in guests if guest.phase == "queued"]
        queue_lengths.add(len(queue))
        assert all(guest.x == QUEUE_X for guest in queue)
        assert all(head.y - tail.y >= QUEUE_SPACING - .001 for head, tail in zip(queue, queue[1:]))
        for guest in guests:
            if guest.phase == "queued" and guest.queued_at is not None:
                joined.setdefault(guest.id, guest.queued_at)
            if guest.phase == "departing" and guest.id not in departed:
                assert lobby.elapsed - joined[guest.id] >= MIN_RECEPTION_SECONDS
                departed.append(guest.id)
            for door in DOORS:
                key = guest.id, door.id
                inside = door.inside_distance(guest.y) > 0
                if previous.get(key, inside) != inside and abs(guest.x - door.x) < door.half_width:
                    crossings.append((tick, door.id, inside))
                previous[key] = inside
    assert len(queue_lengths) >= 3
    assert departed == list(range(len(departed)))
    assert any(tick > 3000 and door == ENTRANCE.id and inside for tick, door, inside in crossings)
    assert all(any(tick > 1500 and door == exit_door.id and not inside for tick, door, inside in crossings)
               for exit_door in EXITS)


def test_queued_guest_rig_uses_the_idle_pose_at_default_time():
    Usd = pytest.importorskip("pxr.Usd")
    from pxr import UsdGeom, UsdSkel

    from domain.isaac_scene import GuestRig

    stage = Usd.Stage.CreateInMemory()
    stage.SetTimeCodesPerSecond(30)
    guest = UsdGeom.Xform.Define(stage, "/World/Guests/Guest01")
    guest.AddTranslateOp()
    guest.AddRotateZOp()
    skeleton = UsdSkel.Skeleton.Define(stage, "/World/Guests/Guest01/Skeleton")
    walk = UsdSkel.Animation.Define(stage, "/World/Animations/Walk")
    walk.GetPrim().GetReferences().AddReference(str(ROOT / "payloads/isaac/assets/downloads/guest_walk.usdc"))
    rig = GuestRig(stage, 1, walk)
    pose = UsdSkel.Animation.Get(stage, "/World/Animations/Guest01Pose")
    traveler = SimpleNamespace(x=0.5, y=2, heading=0, walking=True, walk_time=.2)
    rig.update(traveler)
    assert pose.GetRotationsAttr().Get() == walk.GetRotationsAttr().Get(6)
    traveler.walking = False
    rig.update(traveler)
    assert pose.GetRotationsAttr().Get() == walk.GetRotationsAttr().Get(0)
    assert not pose.GetRotationsAttr().GetTimeSamples()
    assert UsdSkel.BindingAPI(skeleton).GetAnimationSourceRel().GetTargets() == [pose.GetPath()]


def test_robot_marker_decodes_from_calibrated_camera_pixels():
    np = pytest.importorskip("numpy")
    cv2 = pytest.importorskip("cv2")
    Usd = pytest.importorskip("pxr.Usd")
    from pxr import UsdGeom

    from domain.isaac_scene import camera_calibration
    from domain.layout import CAMERAS, RESOLUTION
    from domain.robot import NO_ROBOT, TAG_HEIGHT, TAG_ID, TAG_OFFSET, RobotCamera, patrol_xy

    stage_path = ROOT / "payloads/isaac/assets/hotel_reception.usda"
    stage = Usd.Stage.OpenMasked(str(stage_path), Usd.StagePopulationMask(["/World/Cameras"]))
    models = [camera_calibration(UsdGeom.Camera.Get(stage, path)) for path in CAMERAS]
    camera = RobotCamera(models)
    width, height = RESOLUTION
    atlas = np.full((height * 2, width * 2, 3), 255, dtype=np.uint8)
    assert camera.observe(atlas) == NO_ROBOT

    expected_x, expected_y = patrol_xy(0)
    base = np.array([expected_x + TAG_OFFSET[0], expected_y + TAG_OFFSET[1], TAG_HEIGHT])
    across = np.array([math.sin(math.radians(40)), math.cos(math.radians(40)), 0])
    up = np.array([0, 0, 1])
    corners = [base + .25 * (side * across + elevation * up) for side, elevation in
               ((-1, 1), (1, 1), (1, -1), (-1, -1))]
    projection = np.array(models[3]["projectionMatrix_3x4_w2p"]).reshape(3, 4)
    projected = []
    for corner in corners:
        u, v, depth = projection @ [*corner, 1]
        projected.append([u / depth, v / depth])
    bits = cv2.aruco.generateImageMarker(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50), TAG_ID, 120)
    texture = np.pad(bits, 20, constant_values=255)
    mapping = cv2.getPerspectiveTransform(
        np.float32([[0, 0], [159, 0], [159, 159], [0, 159]]), np.float32(projected),
    )
    camera_frame = cv2.warpPerspective(texture, mapping, RESOLUTION, borderValue=255)
    atlas[height:, width:] = camera_frame[:, :, None]
    x, y, sensor = camera.observe(atlas)
    assert sensor == 3
    assert (x, y) == pytest.approx((expected_x, expected_y), abs=.15)


def feed(observations, camera, frame, xy, *, now, track="22"):
    from domain.nvidia_mv3dt_schema_pb2 import Frame

    packet = Frame(id=str(frame), sensorId=f"Camera{camera + 1}")
    if xy is not None:
        guest = packet.objects.add(id=track)
        guest.bbox3d.coordinates.extend([*xy, .85])
        guest.bbox.leftX, guest.bbox.topY = 20, 30
        guest.bbox.rightX, guest.bbox.bottomY = 60, 180
    observations.ingest(packet.SerializeToString(), now=now, timestamp="2026-11-18T19:00:00Z")


def test_live_room_timer_follows_the_track_across_cameras_and_ends_at_the_exit():
    from domain.layout import ENTRANCE, EXITS
    from domain.observations import Observations

    observed = Observations()
    feed(observed, ENTRANCE.camera, 1, (0, -8.7), now=0)
    assert observed.visible(now=0)[0]["dwell_seconds"] is None
    feed(observed, ENTRANCE.camera, 2, (0, -7.5), now=.5)
    feed(observed, 3, 1, (0, 1), now=32.5)
    feed(observed, 1, 1, (0, 1.1), now=33.2)
    assert {row["dwell_seconds"] for row in observed.visible(now=33.5)} == {33}
    west = EXITS[0]
    feed(observed, west.camera, 1, (west.x, 7.4), now=34)
    feed(observed, west.camera, 2, (west.x, 8.6), now=34.4)
    feed(observed, 3, 2, (west.x, 7.8), now=34.8)
    assert {row["dwell_seconds"] for row in observed.visible(now=35)} == {None}
    feed(observed, ENTRANCE.camera, 3, (0, -8.8), now=37)
    feed(observed, ENTRANCE.camera, 4, (0, -7.4), now=37.6)
    assert observed.visible(now=39)[0]["dwell_seconds"] == 1


def test_metadata_counts_completed_crossings_in_both_directions_and_restores_totals():
    from domain.layout import DOORS
    from domain.observations import Observations

    observed = Observations()
    for index, door in enumerate(DOORS):
        frame = 20 * index + 1
        for delta, offset in enumerate((-.68, -.11, .05, .72, .83, .07, -.66)):
            for camera in range(4):
                xy = (door.x, door.y + offset)
                feed(observed, camera, frame + delta, xy, now=3 * index + .16 * delta)
                feed(observed, camera, frame + delta, xy, now=3 * index + .16 * delta)
            if delta == 3:
                expected = "left" if door.y > 0 else "entered"
                first_crossing = observed.snapshot()["recent_crossings"][0]
                assert (first_crossing["door"], first_crossing["direction"]) == (door.id, expected)
        feed(observed, door.camera, frame + 2, (door.x, door.y + 1), now=3 * index + 1.2)
    counts = observed.snapshot()
    assert (counts["entered"], counts["left"]) == (3, 3)
    assert set(counts["doors"]) == {door.id for door in DOORS}
    assert all(totals == {"entered": 1, "left": 1} for totals in counts["doors"].values())
    assert len(counts["recent_crossings"]) == 6
    schema = json.loads((ROOT / "contracts.json").read_text())["outputs"]["primary"]["schema"]
    Draft202012Validator(schema).validate({"status": "running", **counts})
    resumed = Observations(counts)
    feed(resumed, DOORS[0].camera, 0, (DOORS[0].x, DOORS[0].y + .8), now=12)
    assert resumed.snapshot()["doors"] == counts["doors"]
    assert resumed.snapshot()["recent_crossings"] == counts["recent_crossings"]


def test_metadata_rejects_jitter_wall_crossings_and_tracking_gaps():
    from domain.layout import DOORS
    from domain.observations import Observations

    observed = Observations()
    door = DOORS[0]
    cases = [
        ("11", door.x, [-.59, -.13, .11, -.42], [0, .2, .4, .6]),
        ("12", door.x + door.half_width + .35, [-.69, .72], [.7, .9]),
        ("13", door.x, [-.81, .81], [1, 4]),
        ("14", door.x, [-2.9, .64], [4.1, 4.3]),
        ("15", door.x, [math.nan, .55], [4.5, 4.8]),
    ]
    frame = 0
    for track, x, offsets, times in cases:
        for offset, at in zip(offsets, times):
            frame += 1
            feed(observed, door.camera, frame, (x, door.y + offset), now=at, track=track)
    assert observed.snapshot()["entered"] == observed.snapshot()["left"] == 0


def test_live_hooks_publish_counts_and_release_the_worker_on_stop(tmp_path):
    from domain import live

    run_dir, output_dir = tmp_path / "run", tmp_path / "output"
    block = SimpleNamespace(
        config={}, store=CommittedJsonStore(run_dir), output_directory=output_dir,
        resources={}, environment={}, agent_id="hotel-agent", check=Mock(),
    )
    with (
        patch.object(live, "require_gpu") as gpu,
        patch.object(live, "report_activity") as activity,
        patch.object(live, "CameraStreams") as streams,
        patch.object(live, "Simulation") as simulation,
        patch.object(live, "prepare") as prepare,
        patch.object(live, "detector_ready", return_value=True),
        patch.object(live, "prepare_detector") as detector,
        patch.object(live, "process") as broker,
        patch.object(live, "start_pipeline") as pipeline,
        patch.object(live, "collect"),
        patch.object(live, "Workspace") as workspace,
        patch.object(live, "claim_service_web_ui") as claim,
    ):
        broker.return_value.__enter__.return_value = (Mock(), lambda: "")
        pipeline.return_value.__enter__.return_value = (SimpleNamespace(poll=lambda: None), lambda: "")
        live.start(block, {})
        gpu.assert_called_once()
        detector.assert_called_once()
        claim.assert_called_once()
        prepare.assert_called_once_with(
            simulation.call_args.args[0], streams.return_value.feeds,
            simulation.return_value.wait_for_calibration.return_value,
        )
        assert not live.ready(block, {})
        assert [call.args[0] for call in activity.call_args_list] == [
            "Starting the lobby simulation",
            "Checking live cameras and guest tracking",
        ]
        from domain.layout import ENTRANCE
        observed = block.resources["hotel"].observations
        feed(observed, ENTRANCE.camera, 1, (0, ENTRANCE.y - .6), now=0)
        feed(observed, ENTRANCE.camera, 2, (0, ENTRANCE.y + .6), now=.3)
        with patch.object(observed, "require_recent"):
            simulation.return_value.preview = None
            assert not live.ready(block, {})
            assert activity.call_count == 2
            simulation.return_value.preview = b"camera preview"
            assert live.ready(block, {})
            assert live.ready(block, {})
        assert activity.call_count == 3
        activity.assert_called_with("The lobby is live. Tracking guests and counting arrivals and departures.",
                                    kind="result")
        assert live.cycle(block, {}) == {"entered": 1, "left": 0}
        live.stop(block, {})
        streams.return_value.close.assert_called_once()
        simulation.return_value.close.assert_called_once()
        workspace.return_value.close.assert_called_once()
    receipt = (run_dir / "people_counts.json").read_bytes()
    assert json.loads(receipt)["status"] == "stopped"
    assert json.loads(receipt)["entered"] == 1
    assert (output_dir / "people_counts.json").read_bytes() == receipt
    review = (run_dir / "report.html").read_text()
    assert (output_dir / "report.html").read_text() == review
    assert "1 of 1 recorded door crossings" in review
    assert json.loads(receipt)["recent_crossings"][0]["observed_at"] in review
    assert (output_dir / "people_counts.json").stat().st_mode & 0o777 == 0o644


def test_web_ui_advertises_the_bridge_address_for_the_owner_host():
    from domain.workspace import advertised_url
    from mn_sdk_web_ui import resolve_web_ui_binding

    environment = {
        "MN_DOCKER_WORKER_NETWORK_MODE": "runtime",
        "MN_DOCKER_WORKER_CONTAINER_NAME": "hotel-worker",
    }
    binding = resolve_web_ui_binding(environment=environment)
    with patch("domain.workspace.socket.gethostbyname", return_value="172.19.0.10") as resolve:
        assert advertised_url(binding, 39181, environment) == "http://172.19.0.10:39181/"
    resolve.assert_called_once_with("hotel-worker")
