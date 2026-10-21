"""One native caption admission or operator command; Core owns the sampling loop."""

import json
import subprocess
import time

from mn_live_video_analysis_skill import SamplingPolicy
from mn_sdk.integrations.block_publication_files import publish_files
from mn_sdk_common.publication import ArtifactWrite

from .caption_schedule import claim_caption
from .frame_evidence import capture_batch, publication_writes
from .live_service import DEMO_LAUNCHER
from .monitoring import apply_steering_command, initial_monitoring_state, is_steering_command


def await_demo(config):
    if (config.get("video_source") or {}).get("profile") == "bundled_demo":
        # The resident service owns the publisher and its process group.
        subprocess.run([DEMO_LAUNCHER, "--wait"], check=True,
            stdout=subprocess.DEVNULL, timeout=65)


def _prepare(work):
    monitoring = {**initial_monitoring_state(), **work["state"].get("monitoring", {})}
    payload, events, force = work["payload"], [], False
    steering = is_steering_command(payload)
    if steering:
        payload = {**payload, "command_id": payload.get("command_id") or work["input_key"]}
        try:
            monitoring, event = apply_steering_command(monitoring, payload, now=time.time())
            events.append(event)
            force = event["payload"]["analyze_now"]
        except ValueError as error:
            events.append({"type": "cctv_operator_sample_skipped", "payload": {
                "reason": "invalid_steering", "error": str(error), "command_id": payload["command_id"]}})
    return {"monitoring": monitoring, "events": events, "force": force, "steering": steering}


def _sample(block, prepared, policy):
    started = time.monotonic()
    await_demo(block.config)
    result = claim_caption(block.store.run_dir, block.run_id, monitoring=prepared["monitoring"],
        force=prepared["force"], invocation_id=block.invocation_id)
    if (not isinstance(result, dict) or set(result) != {"state", "batch"}
        or not isinstance(result["state"], dict)):
        raise ValueError("Resident caption admission returned an invalid result")
    evidence = capture_batch(block, result["batch"], max_frames=policy.max_model_frames) if result["batch"] is not None else None
    if not prepared["steering"]:
        remaining = 1 / policy.proxy_fps - (time.monotonic() - started)
        if remaining > 0:
            block.check()
            time.sleep(remaining)
    block.check()
    return {"state": {"monitoring": prepared["monitoring"], "caption_schedule": result["state"]},
        "batch": result["batch"], "evidence": evidence, "scheduled_at": time.time()}


def process(block, work):
    policy = SamplingPolicy.from_mapping(block.config.get("sampling"))
    prepared_path, sampled_path = block.root + "/instruction.json", block.root + "/sample.json"
    prepared = block.read_checkpoint(block.freeze_checkpoint(prepared_path, lambda: _prepare(work)), expected_path=prepared_path)
    # A lost RPC reply retries the same resident claim identity. Only completed
    # admissions are frozen; transport uncertainty must not release the slot.
    sampled = block.read_checkpoint(block.freeze_checkpoint(sampled_path, lambda: _sample(block, prepared, policy)), expected_path=sampled_path)
    state, events, emissions = sampled["state"], list(prepared["events"]), []
    views = {"monitoring_state.json": {"schema": "otterdesk.cctv_operator.monitoring_state.v1", **state["monitoring"]},
             "sampling_state.json": state}
    writes = [ArtifactWrite(name, name, (json.dumps(value, indent=2, sort_keys=True) + "\n").encode(),
        kind="json", authoritative=True) for name, value in views.items()]
    if sampled["evidence"]:
        writes.extend(publication_writes(block, sampled["evidence"]))
        batch = {**sampled["batch"], "frame_evidence": sampled["evidence"]}
        emissions.append({"port": "ready", "value": batch})
        events.append({"type": "cctv_operator_frame_batch_ready", "payload": {**sampled["batch"],
            "summary": "Selected evidence frames for scene analysis", "activity_kind": "milestone", "owner_blueprint": "cctv_operator"}})
    if not prepared["steering"]:
        emissions.append({"port": "next", "value": {"scheduled_at": sampled["scheduled_at"]}})
    return {"state": state, "outputs": {"published_files": publish_files(block, writes)},
        "emissions": emissions, "events": events}
