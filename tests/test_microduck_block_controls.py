"""Real MCP-to-block-to-browser admission, with no browser or live model."""

import asyncio
from dataclasses import replace
import importlib
import json
from pathlib import Path
import threading

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint
from mn_sdk.step_runtime import StepContext

ROOT = Path(__file__).resolve().parents[1] / "microduck_controller"
A, B, C = (f"00000000-0000-4000-8000-00000000000{n}" for n in (1, 2, 3))
MOVE = {
    "segments": [{"direction": "forward", "duration_ms": 250}],
    "move": {"direction": "forward", "duration": "short"},
}


@pytest.fixture
def control_environment(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    manifest = compile_blueprint(read_blueprint(ROOT)).manifest
    descriptor = tmp_path / "runtime.json"
    from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
    descriptor.write_text(json.dumps(resolved_worker_descriptor(read_blueprint(ROOT), manifest)))
    output = tmp_path / "run"
    values = {
        "MN_BLUEPRINT_MANIFEST_PATH": descriptor,
        "MN_RUN_DIR": output,
        "MN_JOB_ID": "duck-job",
        "MN_RUN_ID": "duck-run",
        "MN_AGENT_ID": "run_microduck_service__block_run_microduck_service_specialist",
        "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
        "MN_BLUEPRINT_CONFIG_JSON": "{}",
        "MN_HOME": tmp_path / "home",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, str(value))
    return (
        importlib.import_module("domain.control_blocks"),
        importlib.import_module("domain.bridge"),
        importlib.import_module("services.duck_control_service"),
        output,
    )


async def ready(bridge):
    messages = []

    async def sender(value):
        messages.append(value)

    hub = bridge.BridgeHub()
    await hub.claim("browser", sender)
    await hub.update_state(
        "browser",
        {"ready": True, "duck": {"locomotion": "legs"}, "ball": {"active": True}},
    )
    return hub, messages


def test_real_mcp_dispatch_replays_latest_observed_receipt_and_rejects_conflicting_ids(
    control_environment,
):
    _, bridge, service, output = control_environment

    async def scenario():
        hub, messages = await ready(bridge)
        mcp = service.create_mcp_server(hub, run_dir=output)

        async def call(tool, arguments):
            result = await mcp.call_tool(tool, arguments)
            assert result.is_error is not True
            return result.structured_content["data"]

        arguments = {"command_id": A, "direction": "forward", "duration": "short"}
        first = await call("move_duck", arguments)
        assert first["status"] == "queued" and first["accepted"] is True
        assert len(messages) == 1 and messages[0]["command"]["payload"] == MOVE
        await hub.update_command("browser", {"command_id": A, "status": "completed"})
        assert (await call("move_duck", arguments))["status"] == "completed"
        await hub.disconnect("browser")
        assert (await call("move_duck", arguments))["status"] == "completed"
        changed = await call("move_duck", {**arguments, "direction": "backward"})
        assert changed["reason"] == "command_id_reused_for_different_effect"
        assert len(messages) == 1
        assert list(output.glob("blocks/*/result.json"))

    asyncio.run(scenario())


def test_stop_overtakes_unadmitted_work_and_cancelled_admission_stays_cancelled(
    control_environment, monkeypatch
):
    controls, bridge, _, output = control_environment
    entered, release = threading.Event(), threading.Event()
    from mn_sdk.integrations import block_async

    original = block_async.run_operation

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(block_async, "run_operation", delayed)

    async def scenario():
        hub, messages = await ready(bridge)
        controller = controls.ControlBlocks(hub, output)
        pending = asyncio.create_task(
            controller.enqueue(command_id=A, kind="motion_plan", payload=MOVE)
        )
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            stopped = await asyncio.wait_for(
                controller.enqueue(command_id=B, kind="stop", payload={}), 0.5
            )
            assert stopped["command_id"] == B
        finally:
            release.set()
        result = await pending
        assert result["reason"] == "stopped_by_operator"
        assert (
            await controller.enqueue(command_id=A, kind="motion_plan", payload=MOVE)
        ) == result
        assert [item["command"]["kind"] for item in messages] == ["stop"]

    asyncio.run(scenario())


@pytest.mark.parametrize("restarted", [False, True])
def test_lost_admission_reply_never_repeats_an_uncertain_effect(
    control_environment, monkeypatch, restarted
):
    controls, bridge, service, output = control_environment
    original = bridge.BridgeHub.execute

    async def lose_reply(device, inputs):
        await original(device, inputs)
        raise TimeoutError("injected lost admission response")

    monkeypatch.setattr(bridge.BridgeHub, "execute", lose_reply)

    async def scenario():
        hub, messages = await ready(bridge)
        controller = controls.ControlBlocks(hub, output)
        first = await controller.enqueue(command_id=A, kind="motion_plan", payload=MOVE)
        assert first["status"] == "unknown" and len(messages) == 1
        assert first["state"] == "running" and "accepted" not in first
        if restarted:
            replacement, delivered = await ready(bridge)
            controller = controls.ControlBlocks(replacement, output)
            observed = await controller.status(A)
            assert observed["status"] == "unknown" and observed["state"] == "running"
            mcp = service.create_mcp_server(replacement, run_dir=output)
            polled = await mcp.call_tool("get_operation_status", {"operation_id": A})
            assert polled.is_error is not True
            assert polled.structured_content["data"]["state"] == "running"
        second = await controller.enqueue(
            command_id=A, kind="motion_plan", payload=MOVE
        )
        assert second["status"] == ("unknown" if restarted else "queued")
        assert len(messages) == 1
        if restarted:
            assert delivered == []
        else:
            assert list(output.glob("blocks/*/result.json"))

    asyncio.run(scenario())


def test_run_scope_allows_a_new_run_without_cross_run_command_replay(
    control_environment,
):
    controls, bridge, _, output = control_environment

    async def scenario():
        first_hub, first_messages = await ready(bridge)
        first = controls.ControlBlocks(first_hub, output)
        assert (await first.enqueue(command_id=A, kind="motion_plan", payload=MOVE))[
            "accepted"
        ] is True
        second_hub, second_messages = await ready(bridge)
        context = replace(StepContext.from_environment(), run_id="new-run")
        second = controls.ControlBlocks(
            second_hub, output.parent / "new-run", context=context
        )
        assert (await second.enqueue(command_id=A, kind="motion_plan", payload=MOVE))[
            "accepted"
        ] is True
        assert len(first_messages) == len(second_messages) == 1

    asyncio.run(scenario())


@pytest.mark.parametrize("completed", [False, True])
def test_committed_admission_after_restart_cannot_claim_an_unobserved_motion_result(
    control_environment, completed
):
    controls, bridge, _, output = control_environment

    async def scenario():
        hub, messages = await ready(bridge)
        controller = controls.ControlBlocks(hub, output)
        assert (await controller.enqueue(command_id=A, kind="motion_plan", payload=MOVE))["accepted"] is True
        if completed:
            await hub.update_command("browser", {"command_id": A, "status": "completed"})
        replacement, delivered = await ready(bridge)
        restarted = controls.ControlBlocks(replacement, output)
        result = await restarted.enqueue(command_id=A, kind="motion_plan", payload=MOVE)
        assert result["status"] == "unknown" and "accepted" not in result
        assert (await restarted.status(A))["status"] == "unknown"
        assert len(messages) == 1 and delivered == []

    asyncio.run(scenario())


def test_disconnected_callers_do_not_release_admission_capacity_early(
    control_environment, monkeypatch
):
    controls, bridge, _, output = control_environment
    release, entered = threading.Event(), threading.Event()
    from mn_sdk.integrations import block_async

    original = block_async.run_operation

    def delayed(*args, **kwargs):
        entered.set()
        assert release.wait(3)
        return original(*args, **kwargs)

    monkeypatch.setattr(block_async, "run_operation", delayed)

    async def scenario():
        hub, _ = await ready(bridge)
        controller = controls.ControlBlocks(hub, output)
        first = asyncio.create_task(
            controller.enqueue(command_id=A, kind="motion_plan", payload=MOVE)
        )
        second = asyncio.create_task(
            controller.enqueue(command_id=B, kind="motion_plan", payload=MOVE)
        )
        try:
            assert await asyncio.to_thread(entered.wait, 2)
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
            assert len(controller.runner.pending) == 2
            third = await controller.enqueue(
                command_id=C, kind="motion_plan", payload=MOVE
            )
            assert third["reason"] == "browser_busy"
        finally:
            release.set()
        await second
        remaining = list(controller.runner.pending)
        if remaining:
            await asyncio.gather(*remaining)
        await asyncio.sleep(0)
        assert not controller.runner.pending

    asyncio.run(scenario())
