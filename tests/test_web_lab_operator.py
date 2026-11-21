"""Live workcell source, observations, controls and workspace lifecycle."""

import asyncio
import json
import time
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError
from urllib.request import urlopen
from zipfile import ZipFile

import pytest
from websockets.exceptions import ConnectionClosedError
from websockets.sync.client import connect

from mn_sdk.blueprints import compile_blueprint, export_blueprint, read_blueprint
from mn_sdk_common.committed_artifacts import CommittedJsonStore


ROOT = Path(__file__).resolve().parents[1] / "web_lab_operator"


ASSETS = ROOT / "payloads" / "isaac" / "assets"


@pytest.fixture
def sample_run(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    from domain.sample_run import SampleRun

    return SampleRun()


def snapshot(run, frame):
    observation = run.sample.observe()
    return run.snapshot(frame, observation, observation.pose.mixtures)


def at_step(run, label):
    from domain.dilution import STEPS

    index = next(index for index, step in enumerate(STEPS) if step.label == label)
    run.sample.restart()
    run.sample.advance(sum(step.seconds for step in STEPS[:index]) + STEPS[index].seconds / 2)
    return run.sample.observe()


def test_bundle_compiles_and_exports_the_single_mk3_workcell(tmp_path):
    blueprint = read_blueprint(ROOT)
    compiled = compile_blueprint(blueprint)
    assert compiled.manifest["service"]["run_until"] == "manual_stop"
    assert compiled.manifest["service"]["state_artifact"] == "equipment_state.json"
    assert [step["id"] for step in compiled.manifest["workflow"]["steps"]] == ["check_workcell", "monitor_live_workcell"]
    assert compiled.manifest["workflow"]["edges"]
    assert blueprint.extension("mn.blocks")["steps"]["monitor_live_workcell"]["uses"] == "mn.blocks.monitored_service@1"
    assert blueprint.extension("mn.ui")["web_ui"]["adapter"] == "external-url"
    contract = blueprint.document("contracts")
    assert set(contract["inputs"]) == {"supervisor_instructions"}
    assert contract["outputs"]["primary"]["schema_version"] == "mn.web_lab.state.v2"
    with ZipFile(export_blueprint(blueprint, tmp_path / "workcell.zip")) as bundle:
        assets = {name.removeprefix("payloads/isaac/assets/") for name in bundle.namelist()
                  if name.startswith("payloads/isaac/assets/")}
        assert assets == {"web_lab.usda", "dilution_station.usda", "sample_labels.png", "vendor/mk3_cell.usdc",
                          "vendor/CERN-OHL-S-2.0.txt", "vendor/NOTICE.txt"}


def test_mk3_stage_moves_the_cad_gantry_and_shows_dispensing_and_reading(sample_run):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdUtils
    from domain.dilution_scene import STATION, StageDilution
    from domain.workspace import CAMERAS

    path = ASSETS / "web_lab.usda"
    stage = Usd.Stage.Open(str(path))
    assert stage.HasAuthoredTimeCodeRange()
    assert stage.GetEndTimeCode() > stage.GetStartTimeCode()
    station = StageDilution(stage)
    assert stage.GetPrimAtPath(f"{STATION}/Frame/FrameExtrusions").IsA(UsdGeom.Mesh)
    carriage = f"{STATION}/Gantry/Carriage"
    mount = stage.GetPrimAtPath(f"{carriage}/Tool/Mechanism/ToolMount")
    assert mount.IsA(UsdGeom.Mesh)
    assert not stage.GetPrimAtPath("/World/Equipment")
    assert all(UsdGeom.Camera.Get(stage, camera) for camera in CAMERAS.values())
    _, assets, missing = UsdUtils.ComputeAllDependencies(str(path))
    assert not missing
    assert {Path(asset).name for asset in assets} == {"sample_labels.png"}

    def world_position(prim):
        return UsdGeom.XformCache().GetLocalToWorldTransform(prim).ExtractTranslation()

    station.apply(sample_run.sample.observe())
    start = world_position(mount)
    assert station.tip.GetVisibilityAttr().Get() == "invisible"
    station.apply(at_step(sample_run, "Drawing from Stock"))
    assert world_position(mount)[2] < start[2]
    assert station.tip.GetVisibilityAttr().Get() == "inherited"
    assert station.observe()[0].volume < 2

    station.apply(at_step(sample_run, "Dispensing into 1:2"))
    assert stage.GetEditTarget().GetLayer() == stage.GetSessionLayer()
    assert world_position(mount)[0] > start[0]
    assert station.stream.GetVisibilityAttr().Get() == "inherited"
    assert station.stream.GetHeightAttr().Get() > 0
    tip = stage.GetPrimAtPath(f"{carriage}/Tool/TipEnd")
    stream = station.stream.GetPrim()
    assert tuple(world_position(tip))[:2] == pytest.approx(tuple(world_position(stream))[:2])
    assert .0 < station.observe()[1].concentration < .5

    station.apply(at_step(sample_run, "Checking 1:4"))
    assert station.stream.GetVisibilityAttr().Get() == "invisible"
    assert station.focus_rings[2].ComputeVisibility() == "inherited"
    assert station.focus_rings[1].ComputeVisibility() == "invisible"

    fresh = Usd.Stage.Open(str(path))
    assert world_position(fresh.GetPrimAtPath(mount.GetPath())) == start


def test_reference_check_uses_rendered_usd_color_and_fill(sample_run):
    pytest.importorskip("pxr")
    from pxr import Gf, Usd
    from domain.dilution_scene import StageDilution, liquid_color

    stage = Usd.Stage.Open(str(ASSETS / "web_lab.usda"))
    station = StageDilution(stage)
    sample_run.sample.advance(100)
    observation = sample_run.sample.observe()
    station.apply(observation)
    result = observation.snapshot(station.observe())
    assert result["check"]["status"] == "passed"
    assert [well["concentration_percent"] for well in result["wells"]] == [100, 50, 25, 12.5, 0]

    liquid, _, tint = station.liquids[2]
    tint.Set(Gf.Vec3f(*liquid_color(.4)))
    station.liquids[-1][0].GetHeightAttr().Set(.008)
    result = observation.snapshot(station.observe())
    assert result["check"]["status"] == "needs_review"
    assert result["wells"][2]["concentration_percent"] == 40
    assert result["wells"][2]["issues"] == ["Color differs from target"]
    assert result["wells"][-1]["issues"] == ["Fill differs from target"]
    assert liquid.GetHeightAttr().Get() > 0


def test_sample_conserves_the_mixtures_and_checks_each_vessel(sample_run):
    sample = sample_run.sample
    checked = set()
    for _ in range(240):
        observation = sample.observe()
        liquids = (*observation.pose.mixtures, observation.pose.tip)
        assert sum(liquid.volume for liquid in liquids) == pytest.approx(6)
        assert sum(liquid.dye for liquid in liquids) == pytest.approx(2)
        if observation.reading_index is not None:
            assert observation.transfers == 3
            checked.add(observation.reading_index)
        sample.advance(.17)
    result = snapshot(sample_run, 1)["sample"]
    assert checked == {0, 1, 2, 3, 4}
    assert result["status"] == "complete"
    assert result["completed_transfers"] == result["total_transfers"] == 3
    assert result["check"]["checked"] == result["check"]["total"] == 5


@pytest.mark.parametrize("message", [
    [], {"action": None}, {"action": "move", "joint": "lift", "target": 450},
    {"action": "home"}, {"action": "hold"}, {"action": "lid", "enabled": True},
    {"action": "light", "enabled": True}, {"action": "restart_sample", "steps": []},
])
def test_rejects_commands_outside_sample_controls(sample_run, message):
    from domain.sample_run import CommandError, command_from_message

    with pytest.raises(CommandError, match="Stop sample or Run sample again"):
        command_from_message(message)


def test_sample_stop_and_replay_follow_the_rendered_revision(sample_run):
    from domain.sample_run import CommandError
    from domain.workspace import LiveFrames

    frames = LiveFrames()
    stop = {"revision": 0, "command": {"action": "stop_sample"}}
    with pytest.raises(CommandError, match="current Isaac Sim frame"):
        frames.submit(stop)
    before = at_step(sample_run, "Dispensing into 1:2").pose
    frames.publish(snapshot(sample_run, 1), {})
    with pytest.raises(CommandError, match="Stop the current sample"):
        frames.submit({"revision": 0, "command": {"action": "restart_sample"}})
    assert frames.submit(stop) == 1
    with pytest.raises(CommandError, match="controls changed"):
        frames.submit(stop)
    sample_run.apply(*frames.command())
    sample_run.sample.advance(10)
    assert sample_run.sample.observe().pose == before
    assert not sample_run.sample.observe().flow
    stopped = snapshot(sample_run, 2)
    assert stopped["sample"]["status"] == "stopped"
    frames.publish(stopped, {})
    assert frames.command() is None
    with pytest.raises(CommandError, match="controls changed"):
        frames.submit(stop)
    assert frames.submit({"revision": 1, "command": {"action": "restart_sample"}}) == 2
    sample_run.apply(*frames.command())
    restarted = snapshot(sample_run, 3)
    assert restarted["sample"]["status"] == "running"
    assert restarted["sample"]["check"]["checked"] == 0
    assert [well["concentration_percent"] for well in restarted["sample"]["wells"]] == [100, 0, 0, 0, 0]
    frames.publish(restarted, {})
    frames.last_frame_at -= 10
    with pytest.raises(CommandError, match="current Isaac Sim frame"):
        frames.submit({**stop, "revision": 2})


def test_workspace_streams_camera_and_observed_sample_control(sample_run, monkeypatch):
    from domain.workspace import LiveFrames, Workspace

    def kit_run(coroutine):
        coroutine.close()
        raise RuntimeError("The workspace must leave Kit's asyncio.run wrapper alone.")

    monkeypatch.setattr(asyncio, "run", kit_run)
    frames = LiveFrames()
    frames.publish(snapshot(sample_run, 1), {"overview": b"overview", "samples": b"samples"})
    workspace = Workspace("127.0.0.1", 0, frames)
    base = f"127.0.0.1:{workspace.port}"
    try:
        with urlopen(f"http://{base}/", timeout=3) as response:
            assert b"OLA MK3 workcell" in response.read()
        with urlopen(f"http://{base}/session.json", timeout=3) as response:
            assert response.headers["Cache-Control"] == "no-store"
            assert response.headers["Cross-Origin-Resource-Policy"] == "same-origin"
            key = json.load(response)["key"]
        with pytest.raises(HTTPError, match="404"):
            urlopen(f"http://{base}/anything.usda", timeout=3)
        with connect(f"ws://{base}/control", open_timeout=3) as unauthenticated:
            unauthenticated.send('{"key":"wrong"}')
            with pytest.raises(ConnectionClosedError, match="1008"):
                unauthenticated.recv(timeout=3)
        with connect(f"ws://{base}/control", open_timeout=3) as viewer:
            viewer.send(json.dumps({"key": key}))
            assert json.loads(viewer.recv(timeout=3))["state"]["frame"] == 1
            assert viewer.recv(timeout=3) == b"overview"
            viewer.send('{"camera":"samples"}')
            assert json.loads(viewer.recv(timeout=3))["camera"] == "samples"
            assert viewer.recv(timeout=3) == b"samples"

            viewer.send('{"revision":0,"command":{"action":"stop_sample"}}')
            assert json.loads(viewer.recv(timeout=3)) == {"type": "accepted", "id": 1}
            sample_run.apply(*frames.command())
            frames.publish(snapshot(sample_run, 2), {"overview": b"next overview", "samples": b"next samples"})
            observed = json.loads(viewer.recv(timeout=3))["state"]
            assert observed["sample"]["status"] == "stopped"
            assert observed["recent_actions"][0]["id"] == 1
            assert viewer.recv(timeout=3) == b"next samples"

        with connect(f"ws://{base}/control", open_timeout=3) as next_viewer:
            next_viewer.send(json.dumps({"key": key}))
            assert json.loads(next_viewer.recv(timeout=3))["state"] == observed
            assert next_viewer.recv(timeout=3) == b"next overview"
    finally:
        workspace.close()
    assert not workspace.thread.is_alive()


def test_service_claim_requires_a_render_and_shutdown_publishes_the_last_observation(sample_run, monkeypatch, tmp_path):
    from domain import live

    claims, stopped = [], []
    monkeypatch.setattr(live, "claim_service_web_ui", lambda _block, **claim: claims.append(claim))
    monkeypatch.setattr(live, "report_activity", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(live, "mark_agent_progress", lambda: None)
    block = SimpleNamespace(
        config={}, environment={}, agent_id="lab-worker", resources={},
        store=CommittedJsonStore(tmp_path / "run"), output_directory=tmp_path / "output",
    )
    lab = live.LabSession(block)
    block.resources["lab"] = lab
    lab.temporary = SimpleNamespace(cleanup=lambda: None)
    lab.work = tmp_path
    lab.process = SimpleNamespace(poll=lambda: None)
    assert live.ready(block, {}) is False
    assert not claims

    observed = snapshot(sample_run, 2)
    (tmp_path / "state.json").write_text(json.dumps({"port": 5100, "state": observed}))
    assert live.ready(block, {}) and live.ready(block, {})
    assert len(claims) == 1
    assert claims[0]["http_ports"] == claims[0]["websocket_ports"] == [5100]
    assert live.cycle(block, {}) == {"frame": 2}

    def stop_process(process, _work):
        for path in lab.locations:
            assert json.loads(path.read_text()) == {**observed, "status": "stopped"}
        stopped.append(process)

    monkeypatch.setattr(live, "stop_process", stop_process)
    live.stop(block, {})
    assert stopped == [lab.process]
    for path in lab.locations:
        assert json.loads(path.read_text()) == {**observed, "status": "stopped"}


def test_render_heartbeat_failure_remains_visible(sample_run, tmp_path):
    from domain import live

    block = SimpleNamespace(config={}, environment={}, store=CommittedJsonStore(tmp_path / "run"),
                            output_directory=tmp_path / "output")
    lab = live.LabSession(block)
    lab.work = tmp_path
    lab.process = SimpleNamespace(poll=lambda: None)
    lab.state = snapshot(sample_run, 1)
    lab.last_frame_at = time.monotonic() - live.FRAME_TIMEOUT - 1
    with pytest.raises(RuntimeError, match="stopped sending live camera frames"):
        lab.check()
    assert lab.failed
