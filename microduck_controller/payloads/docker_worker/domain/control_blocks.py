"""Bounded command admission through SDK blocks; browser receipts stay live."""

from concurrent.futures import CancelledError
from pathlib import Path
import time

from mn_sdk.integrations.block_async import AsyncBlockOperation
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import (
    CommittedJsonStore,
    CommittedArtifactConflict,
)
from mn_blueprint_blocks.contracts import BlockError

from .protocol import (
    ProtocolError,
    MOVE_DURATIONS_MS,
    MOTION_ROUTINES,
    validate_command_id,
    validate_motion_plan,
    validate_locomotion,
    validate_posture,
    validate_ball_action,
)


class ControlBlocks:
    def __init__(self, hub, run_dir, *, context=None):
        self.hub = hub
        self.run_dir = Path(run_dir)
        self.context = context or StepContext.from_environment()
        self.runner = AsyncBlockOperation(
            self.context,
            operation_id="simulator_command",
            run_dir=self.run_dir,
        )

    async def enqueue(self, *, command_id, kind, payload):
        if kind == "stop":
            # Stop never waits for a file lock or ordinary admission capacity.
            self.runner.invalidate_pending()
            return await self.hub.enqueue(
                command_id=command_id, kind=kind, payload=payload
            )
        try:
            result = await self.runner.invoke(
                request_id=command_id,
                inputs={"command_id": command_id, "kind": kind, "payload": payload},
                resources={"hub": self.hub},
            )
            admission = CommittedJsonStore(self.run_dir).read(result.outputs["result"])[
                "receipt"
            ]
            # A journal proves admission, never completed motion. Preserve
            # updated browser results and explicit unknowns after restart.
            return (
                (
                    (
                        await self.hub.receipt_for(
                            command_id=command_id, kind=kind, payload=payload
                        )
                    )
                    or self.hub._rejected_receipt(command_id, kind, "command_not_found")
                )
                if admission.get("accepted")
                else admission
            )
        except CommittedArtifactConflict:
            return self.hub._rejected_receipt(
                command_id, kind, "command_id_reused_for_different_effect"
            )
        except BlockError as exc:
            if exc.code in {"device_unavailable", "stale_state", "policy_rejected"}:
                return self.hub._rejected_receipt(command_id, kind, "browser_not_ready")
            if exc.code == "capacity_exceeded":
                return self.hub._rejected_receipt(command_id, kind, "browser_busy")
            if exc.code != "outcome_unknown":
                raise
            return self._unknown(command_id, kind)
        except (TimeoutError, CancelledError):
            return self._unknown(command_id, kind)

    def _unknown(self, command_id, kind):
        # Keep the supervising operation observable without asserting that the
        # device accepted or completed a command whose reply was lost.
        return {
            "schema_version": "mn.microduck.command_receipt.v1",
            "command_id": command_id,
            "kind": kind,
            "status": "unknown",
            "state": "running",
            "reason": "command_outcome_unknown",
            "message": "The command outcome is unverified. Read its operation status before requesting another effect.",
        }

    async def status(self, command_id):
        receipt = await self.hub.command_status(command_id)
        if receipt.get("reason") != "command_not_found":
            return receipt
        observed = await self.runner.inspect(request_id=command_id)
        return (
            self._unknown(command_id, "unknown")
            if observed["status"] != "not_seen"
            else receipt
        )


def validate(block, inputs):
    identifier, kind, payload = (
        validate_command_id(inputs["command_id"]),
        inputs["kind"],
        inputs["payload"],
    )
    if kind == "motion_plan":
        segments = validate_motion_plan(payload.get("segments"))
        if set(payload) == {"segments", "move"}:
            move = payload["move"]
            if (
                set(move) != {"direction", "duration"}
                or move["duration"] not in MOVE_DURATIONS_MS
            ):
                raise ProtocolError("Invalid named move")
            expected = [
                {
                    "direction": move["direction"],
                    "duration_ms": MOVE_DURATIONS_MS[move["duration"]],
                }
            ]
        elif (
            set(payload) == {"segments", "routine"}
            and payload["routine"] in MOTION_ROUTINES
        ):
            expected = MOTION_ROUTINES[payload["routine"]]
        else:
            raise ProtocolError("Invalid bounded motion payload")
        if segments != expected:
            raise ProtocolError("Motion differs from its named control")
    elif kind in {"find_ball", "free_play", "reset"}:
        if payload:
            raise ProtocolError("This command requires an empty payload")
    elif kind == "set_locomotion" and set(payload) == {"locomotion"}:
        validate_locomotion(payload["locomotion"])
    elif kind == "set_posture" and set(payload) == {"posture"}:
        validate_posture(payload["posture"])
    elif kind == "ball_action" and set(payload) == {"action"}:
        validate_ball_action(payload["action"])
    else:
        raise ProtocolError("Unsupported simulator command")
    return {
        "request_id": identifier,
        "kind": kind,
        "payload": payload,
        "effect": "motion"
        if kind in {"motion_plan", "find_ball", "free_play"}
        else "write",
    }


def policy(block, inputs):
    return inputs["state"].get("ready") is True


def receipt(block, inputs):
    return block.observe("command_receipt", inputs, key=inputs["request_id"])


def command_receipt(block, inputs):
    resources = block.resources
    value = resources["async_operation"].call(
        lambda: resources["hub"].receipt_for(
            command_id=inputs["request_id"],
            kind=inputs["kind"],
            payload=inputs["payload"],
        )
    )
    return (
        {"request_id": inputs["request_id"], "receipt": value}
        if value is not None
        else None
    )


def device_state(block, inputs):
    resources = block.resources
    state = resources["async_operation"].call(resources["hub"].state)
    age = state["connection"]["state_age_ms"]
    return {
        **state,
        "connected": state["connection"]["connected"],
        "observed_at": time.time() - (age or 0) / 1000,
    }


def command(block, inputs):
    resources = block.resources
    hub = resources["hub"]

    async def admit():
        if not resources["async_operation"].is_current():
            receipt = hub._rejected_receipt(
                inputs["request_id"], inputs["kind"], "stopped_by_operator"
            )
        else:
            receipt = await hub.enqueue(
                command_id=inputs["request_id"],
                kind=inputs["kind"],
                payload=inputs["payload"],
            )
        return {"request_id": inputs["request_id"], "receipt": receipt}

    return resources["async_operation"].call(admit)


def reconcile(block, request):
    inputs = request["data"]
    resources = block.resources
    receipt = resources["async_operation"].call(
        lambda: resources["hub"].command_status(inputs["request_id"])
    )
    if receipt.get("reason") == "command_not_found":
        return {"state": "unknown"}
    return {
        "state": "succeeded",
        "value": {"request_id": inputs["request_id"], "receipt": receipt},
    }
