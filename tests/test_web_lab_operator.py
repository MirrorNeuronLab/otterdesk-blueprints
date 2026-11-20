"""Live workcell source, observations, controls and workspace lifecycle."""

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


@pytest.fixture
def equipment(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    from domain.equipment import Equipment, Joint

    return Equipment({
        "lift": Joint("Lift", "mm", 330, 540, 450, 100),
        "shoulder": Joint("Shoulder", "°", -146, -72, -127, 40),
        "lid": Joint("Inspection lid", "°", -72, 0, 0, 105),
    })


def test_bundle_compiles_preflight_and_live_service_and_exports_both_usd_layers(tmp_path):
    blueprint = read_blueprint(ROOT)
    compiled = compile_blueprint(blueprint)
    assert compiled.manifest["service"]["run_until"] == "manual_stop"
    assert compiled.manifest["service"]["state_artifact"] == "equipment_state.json"
    assert [step["id"] for step in compiled.manifest["workflow"]["steps"]] == ["check_workcell", "monitor_live_workcell"]
    assert compiled.manifest["workflow"]["edges"]
    assert blueprint.extension("mn.blocks")["steps"]["monitor_live_workcell"]["uses"] == "mn.blocks.monitored_service@1"
    assert blueprint.extension("mn.ui")["web_ui"]["adapter"] == "external-url"
    assert set(blueprint.document("contracts")["inputs"]) == {"supervisor_instructions"}
    with ZipFile(export_blueprint(blueprint, tmp_path / "workcell.zip")) as bundle:
        assert sorted(name for name in bundle.namelist() if name.endswith(".usda")) == [
            "payloads/isaac/assets/andrew_plus.usda",
            "payloads/isaac/assets/web_lab.usda",
        ]


def test_actual_stage_joints_remain_editable_in_the_session_layer(equipment):
    pytest.importorskip("pxr")
    from pxr import Usd, UsdGeom, UsdUtils
    from domain.isaac_scene import CAMERAS, StageEquipment

    path = ROOT / "payloads" / "isaac" / "assets" / "web_lab.usda"
    stage = Usd.Stage.Open(str(path))
    rig = StageEquipment(stage)
    starting_pose, light = rig.observe()
    assert not light
    target = {"lift": 512, "shoulder": -100, "elbow": 50, "wrist": 25, "lid": -72}
    rig.apply(target, True)
    assert rig.observe() == (target, True)
    assert stage.GetEditTarget().GetLayer() == stage.GetSessionLayer()
    assert StageEquipment(Usd.Stage.Open(str(path))).observe() == (starting_pose, False)
    assert all(UsdGeom.Camera.Get(stage, path) for path in CAMERAS.values())
    assert not UsdUtils.ComputeAllDependencies(str(path))[2]


@pytest.mark.parametrize("message", [
    [],
    {"action": "move", "joint": "lift", "target": True},
    {"action": "move", "joint": "lift", "target": 10**400},
    {"action": "move", "joint": "lift", "target": float("nan")},
    {"action": "move", "joint": "lift", "target": 541},
    {"action": "move", "joint": "lid", "target": 0},
    {"action": "move", "joint": ["lift"], "target": 540},
    {"action": "light", "enabled": "false"},
    {"action": "home", "path": "/World"},
])
def test_rejects_values_and_fields_outside_manual_controls(equipment, message):
    from domain.equipment import CommandError, command_from_message

    with pytest.raises(CommandError):
        command_from_message(message, equipment.joints)


def test_motion_hold_and_home_use_current_pose_and_keep_independent_controls(equipment):
    equipment.apply(1, {"action": "move", "joint": "lift", "target": 540})
    equipment.advance(.2)
    assert equipment.position["lift"] == 470
    assert equipment.snapshot(1, equipment.position, False)["motion"] == "moving"
    equipment.apply(2, {"action": "hold"})
    equipment.advance(1)
    held = equipment.snapshot(2, equipment.position, False)
    assert held["motion"] == "held"
    assert held["joints"]["lift"]["value"] == held["joints"]["lift"]["target"] == 470
    equipment.apply(3, {"action": "lid", "enabled": True})
    equipment.apply(4, {"action": "light", "enabled": True})
    equipment.apply(5, {"action": "home"})
    equipment.advance(1)
    assert equipment.position == {"lift": 450, "shoulder": -127, "lid": -72}
    assert equipment.light_on


def test_stale_or_concurrent_commands_cannot_overwrite_an_observed_command(equipment):
    from domain.equipment import CommandError
    from domain.workspace import LiveFrames

    frames = LiveFrames(equipment.joints)
    request = {"revision": 0, "command": {"action": "home"}}
    with pytest.raises(CommandError, match="current Isaac Sim frame"):
        frames.submit(request)
    frames.publish(equipment.snapshot(1, equipment.position, False), {})
    assert frames.submit(request) == 1
    with pytest.raises(CommandError, match="controls changed"):
        frames.submit(request)
    equipment.apply(*frames.command())
    frames.publish(equipment.snapshot(2, equipment.position, False), {})
    assert frames.command() is None
    with pytest.raises(CommandError, match="controls changed"):
        frames.submit(request)
    frames.last_frame_at -= 10
    with pytest.raises(CommandError, match="current Isaac Sim frame"):
        frames.submit({**request, "revision": 1})


def test_workspace_streams_current_observations_and_manual_receipts(equipment):
    from domain.workspace import LiveFrames, Workspace

    frames = LiveFrames(equipment.joints)
    frames.publish(equipment.snapshot(1, equipment.position, False), {"overview": b"overview", "deck": b"deck"})
    workspace = Workspace("127.0.0.1", 0, frames)
    base = f"127.0.0.1:{workspace.port}"
    try:
        with urlopen(f"http://{base}/", timeout=3) as response:
            assert b"Web lab live" in response.read()
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
            viewer.send('{"camera":"deck"}')
            assert json.loads(viewer.recv(timeout=3))["camera"] == "deck"
            assert viewer.recv(timeout=3) == b"deck"

            viewer.send('{"revision":0,"command":{"action":"light","enabled":true}}')
            assert json.loads(viewer.recv(timeout=3)) == {"type": "accepted", "id": 1}
            equipment.apply(*frames.command())
            frames.publish(equipment.snapshot(2, equipment.position, equipment.light_on),
                           {"overview": b"next overview", "deck": b"next deck"})
            observed = json.loads(viewer.recv(timeout=3))["state"]
            assert observed["inspection_light"]
            assert observed["recent_actions"][0]["id"] == 1
            assert viewer.recv(timeout=3) == b"next deck"

        with connect(f"ws://{base}/control", open_timeout=3) as next_viewer:
            next_viewer.send(json.dumps({"key": key}))
            assert json.loads(next_viewer.recv(timeout=3))["state"] == observed
            assert next_viewer.recv(timeout=3) == b"next overview"
    finally:
        workspace.close()
    assert not workspace.thread.is_alive()


def test_service_claim_requires_a_render_and_shutdown_publishes_the_last_observation(equipment, monkeypatch, tmp_path):
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

    observed = equipment.snapshot(2, equipment.position, False)
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


def test_render_heartbeat_failure_remains_visible(equipment, tmp_path):
    from domain import live

    block = SimpleNamespace(config={}, environment={}, store=CommittedJsonStore(tmp_path / "run"),
                            output_directory=tmp_path / "output")
    lab = live.LabSession(block)
    lab.work = tmp_path
    lab.process = SimpleNamespace(poll=lambda: None)
    lab.state = equipment.snapshot(1, equipment.position, False)
    lab.last_frame_at = time.monotonic() - live.FRAME_TIMEOUT - 1
    with pytest.raises(RuntimeError, match="stopped sending live camera frames"):
        lab.check()
    assert lab.failed
