"""Native sampled-vision transition with durable inference and accepted publication."""

import base64
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from mn_blueprint_blocks.context import Capability
from mn_live_video_analysis_skill import SamplingPolicy, redact_source_uri
from mn_sdk.integrations.block_model_request import model_request, model_response_metadata
from mn_sdk.integrations.block_publication_files import publish_files
from mn_sdk_common.prompts import PromptLibrary
from mn_sdk_common.publication import ArtifactWrite

from . import camera_sources, vision_model
from .alert_delivery import alert_text, post_slack
from .benchmarks import Benchmarks
from .caption_schedule import acknowledge_caption
from .conversation_snapshot import event_snapshot
from .cosmos_access import cosmos_slot
from .detection_policy import (configured_alert_policy, configured_monitoring_goal,
    configured_target_notice, configured_visual_targets, evaluate_alert)
from .frame_evidence import read_batch
from .goal_events import goal_event
from .helmet_findings import validate_helmet_goal
from .monitoring import load_monitoring_state
from .observations import frame_observed_event, initial_state, update_conversation_context
from .runtime_memory import CameraMemory, with_history
from .site_monitoring import admission, context as site_context, enrich, notice_state, record_notice
from .video_understanding import batch_context, temporal_prompt
from .visual_detection import normalize_attention_instruction

PROMPTS = PromptLibrary.from_script(__file__, parents_up=1)


def _freeze(block, name, produce):
    path = block.root + "/" + name + ".json"
    return block.read_checkpoint(block.freeze_checkpoint(path, produce), expected_path=path)


def _prepare(block, work, batch, frames, view, metrics):
    analysis_mode = admission(batch, block.config)
    payload, state, events = work["payload"], {**initial_state(), **deepcopy(work["state"])}, []
    state.pop("last_result", None)
    camera = payload["camera_id"]
    revision = int(payload["instruction_revision"])
    if revision >= int(state.get("instruction_revision") or 0):
        instruction = normalize_attention_instruction(payload["instruction"])
        if instruction != state["attention_instruction"]:
            state.update(last_alert_wall_ts=0.0, notified_goal=None)
            events.append({"type": "cctv_operator_attention_updated", "payload": {
                "camera_id": camera, "attention_instruction": instruction,
                "attention_targets": [instruction] if instruction else [], "instruction_revision": revision,
                "cleared": not bool(instruction), "summary": "Operator attention request updated: " + instruction if instruction else "Operator attention request cleared."}})
        state.update(attention_instruction=instruction, attention_targets=[instruction] if instruction else [], instruction_revision=revision,
            last_attention_update={"camera_id": camera, "instruction": instruction, "instruction_revision": revision, "updated_at_wall_ts": block.wall_time()})
    instruction = state["attention_instruction"]
    goal = instruction or configured_monitoring_goal(block.config)
    targets = configured_visual_targets(block.config)
    source = batch["source"]
    uri = redact_source_uri(str(source.get("uri") or ""))
    key = hashlib.sha256(uri.encode()).hexdigest()
    memory = CameraMemory(block.config, view, camera, key)
    try:
        with metrics.measure("memory.recall", variant="MN / Membrane authored captions"):
            history = memory.recall(payload["tick_seq"])
        recall = {"packet": history, "receipt": memory.last_recall_receipt} if memory.memory is not None else None
    finally:
        memory.close()
    capture = batch_context(batch)
    prompt = PROMPTS.render("visual-detection.md", target_description=goal,
        attention_instruction="Operator attention request: " + goal if goal else "Operator attention request: none.", camera_id=camera)
    prompt += "\n\nFacility review policy (operator configuration, not image evidence):\n" + json.dumps(site_context(block.config), ensure_ascii=False)
    started_at = block.wall_time()
    prepared = vision_model.prepare(block, frames, with_history(temporal_prompt(prompt, capture), history))
    return {"state": state, "events": events, "camera": camera, "source_key": key, "source_uri": uri,
        "goal": goal, "instruction": instruction, "targets": targets, "capture": capture,
        "analysis_mode": analysis_mode, "model": prepared, "recall": recall,
        "policy": configured_alert_policy(block.config, visual_targets=targets), "started_at": started_at}


def _analyze(block, prepared, payload, batch, view, raw, metadata):
    state, events = deepcopy(prepared["state"]), list(prepared["events"])
    camera, frame = prepared["camera"], payload["tick_seq"]
    now = metadata["completed_at"]
    observed_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
    try:
        detection = vision_model.interpret(raw, prepared["model"])
        detection = validate_helmet_goal(enrich(detection, batch, block.config,
            prepared["goal"], prepared["instruction"]), prepared["goal"], batch)
        matched = goal_event(detection, batch)
        source = batch["source"]
        latency = max(0, int((now - prepared["started_at"]) * 1000))
        latest = {"schema": "otterdesk.cctv_operator.latest_frame.v2", "batch_id": batch["batch_id"],
            "trigger": batch["trigger"], "instruction_revision": batch["instruction_revision"],
            "source_timestamp": batch["selected_frames"][-1]["timestamp"], "frame_path": batch["selected_frames"][-1]["path"],
            "model_latency_ms": latency, "analyzed_at": observed_at}
        observation = {**detection, **prepared["capture"], "observed_at": matched["observed_at"] if matched else prepared["capture"]["capture_ended_at"],
            "goal_event": matched, "monitoring_goal": prepared["goal"], "analyzed_at": observed_at,
            "source_profile": (block.config.get("video_source") or {}).get("profile", "external"),
            "camera_id": camera, "frame_seq": frame, "video_position_seconds": round(float(source.get("position_seconds") or 0), 3),
            "source_mode": "stream", "source_uri": prepared["source_uri"], "source_name": source.get("name") or prepared["source_uri"] or "unknown",
            "source_index": 0, "source_count": 1, "source_duration_seconds": None, "media_accelerator": "nvidia_cuda", "stream_id": None,
            "attention_instruction": prepared["instruction"], "instruction_revision": payload["instruction_revision"], "sampling_trigger": batch["trigger"],
            "frame_batch_ref": payload["frame_batch_ref"], "batch_id": batch["batch_id"], "candidate_count": batch["candidate_count"],
            "selected_count": batch["selected_count"], "command_id": payload["command_id"], "model_latency_ms": latency,
            "sampling_metrics": batch.get("metrics") or {}, "latest_analyzed_frame": latest,
            "condition_screening": {"route": "deep_analysis", "mode": prepared["analysis_mode"]}, "configured_targets": prepared["targets"]}
        episode = (batch.get("candidate_gate") or {}).get("episode")
        if episode is not None and episode != state.get("gate_episode"):
            state.update(notified_goal=None, gate_episode=episode)
        policy = prepared["policy"]
        decision = evaluate_alert(observation, policy, notice_state(observation, batch, block.config, policy,
            state, prepared["goal"], prepared["instruction"]), active_goal=prepared["goal"], now=now)
        if int(load_monitoring_state(block.store.run_dir).get("instruction_revision") or 0) > payload["instruction_revision"]:
            decision.update(notify=False, reason="superseded_monitoring_instruction")
        observation.update(matched_alert_targets=list(decision["matched_targets"]), alert_decision=decision)
        if decision["notify"]:
            observation["event_image"] = event_snapshot(view, matched, run_id=block.run_id, camera_id=camera, frame_seq=frame)
        projected = update_conversation_context(state, observation)
        events.append({"type": "cctv_operator_deep_analysis_completed", "payload": {
            "camera_id": camera, "frame_seq": frame, "frame_batch_ref": payload["frame_batch_ref"],
            "detected_target": detection["detected_target"], "analysis_mode": prepared["analysis_mode"]}})
        if decision["notify"]:
            notice = configured_target_notice(observation, decision)
            events.append({"type": notice["type"], "payload": notice["payload"]})
            state.update(last_alert_wall_ts=decision["evaluated_at"], notified_goal=prepared["goal"])
            record_notice(observation, state, decision["evaluated_at"])
        elif not detection["detected_target"] and detection["confidence"] >= policy["min_confidence"] and detection.get("goal_validation") != "missing_helmet_evidence_unavailable":
            state["notified_goal"] = None
        events.append(frame_observed_event(projected, state["conversation_context"]["what_happened"]))
        if detection["detected_target"]:
            state.update(detections=int(state["detections"]) + 1, last_detection=observation, last_detection_report=observation["detection_report"])
            events.append({"type": "cctv_operator_detection", "payload": observation})
        state.update(last_error=None, frames_seen=int(state["frames_seen"]) + 1,
            last_batch={"batch_id": batch["batch_id"], "frame_batch_ref": payload["frame_batch_ref"],
                "frame_evidence": payload["frame_evidence"], "sampling_trigger": batch["trigger"], "instruction_revision": payload["instruction_revision"],
                "candidate_count": batch["candidate_count"], "selected_count": batch["selected_count"],
                "model_latency_ms": latency, "sampling_metrics": batch.get("metrics") or {}})
        return {"state": state, "events": events, "observation": observation, "latest": latest}
    except (ValueError, TypeError, KeyError) as error:
        state["last_error"] = str(error)[:800]
        events.append({"type": "cctv_operator_frame_analysis_failed", "payload": {
            "camera_id": camera, "frame_seq": frame, "observed_at": observed_at, "source_uri": prepared["source_uri"],
            "source_mode": "stream", "error": state["last_error"]}})
        return {"state": state, "events": events, "observation": None, "latest": None}


def process(block, work):
    payload, previous = work["payload"], work["state"]
    batch, frames, view = read_batch(block, payload.get("frame_evidence"), payload,
        max_frames=SamplingPolicy.from_mapping(block.config.get("sampling")).max_model_frames)
    if (previous.get("last_batch") or {}).get("batch_id") == batch["batch_id"]:
        if previous["last_batch"].get("frame_evidence") != payload["frame_evidence"]:
            raise ValueError("An already analyzed batch changed its evidence")
        return {"state": previous}
    metrics = Benchmarks(block.store.run_dir, block.config)
    prepared = _freeze(block, "vision-request", lambda: _prepare(block, work, batch, frames, view, metrics))
    with cosmos_slot(block.store.run_dir):
        raw = model_request(block, prepared["model"]["request"], key="scene")
    metadata = model_response_metadata(block, prepared["model"]["request"], key="scene")
    metrics.record("caption.inference", metadata["duration_seconds"] * 1000,
        variant=prepared["model"]["request"]["model"], sample_key=block.invocation_id + ":inference",
        metadata={"frames": len(frames), "instruction_revision": batch["instruction_revision"]})
    analyzed = _freeze(block, "vision-observation", lambda: _analyze(block, prepared, payload, batch, view, raw, metadata))
    state, events, writes = deepcopy(analyzed["state"]), list(analyzed["events"]), []
    observation = analyzed["observation"]
    if observation is not None:
        memory = CameraMemory(block.config, view, prepared["camera"], prepared["source_key"])
        try:
            block.register_capability("camera_memory", Capability(lambda request: memory.remember(request.data, publish=False), block.revision, idempotent=True))
            with metrics.measure("memory.write", variant="MN / Membrane authored captions"):
                recorded = block.invoke("camera_memory", observation, key="observation")
        finally:
            memory.close()
        if recorded is not None:
            state["camera_source"], source = camera_sources.project(block, state.get("camera_source"), recorded)
            writes.append(source)
            writes.append(ArtifactWrite("memory-observation", f"runtime_memory/frame-{payload['tick_seq']}-observation.json",
                json.dumps(recorded, sort_keys=True).encode(), kind="json", authoritative=True))
        writes.extend([ArtifactWrite("latest-frame", "latest_analyzed_frame.jpg", frames[-1], kind="jpeg", authoritative=True),
            ArtifactWrite("latest-metadata", "latest_analyzed_frame.json", json.dumps(analyzed["latest"], sort_keys=True).encode(), kind="json", authoritative=True)])
        if observation.get("event_image"):
            content = base64.b64decode(observation["event_image"]["data"], validate=True)
            writes.append(ArtifactWrite("event-frame", "web/events/" + hashlib.sha256(content).hexdigest() + ".jpg", content, kind="jpeg", authoritative=True))
        env = block.environment or {}
        if observation["alert_decision"]["notify"] and (prepared["policy"]["mode"] == "human_notice_and_slack" or env.get("SLACK_ALERT_ENABLED", "false").lower() in {"1", "true", "yes", "on"}):
            block.register_capability("operator_slack", Capability(lambda request: list(post_slack(request.data["text"], enabled=True)), block.revision))
            status, detail = block.invoke("operator_slack", {"text": alert_text(prepared["camera"], observation, payload["tick_seq"], prepared["source_uri"])}, key="notice")
            events.append({"type": "cctv_operator_slack_alert_" + status, "payload": {**detail, "frame_seq": payload["tick_seq"],
                "camera_id": prepared["camera"], "observed_at": observation["observed_at"], "matched_targets": observation["matched_alert_targets"]}})
    if prepared["recall"] is not None:
        writes.append(ArtifactWrite("memory-recall", f"runtime_memory/frame-{payload['tick_seq']}-recall.json", json.dumps(prepared["recall"], sort_keys=True).encode(), kind="json", authoritative=True))
    packet = block.store.commit(block.root + "/observation.json", {"schema": "otterdesk.cctv.observation.v1",
        "scope": {"job_id": block.job_id, "run_id": block.run_id}, "state": state, "events": events}, kind="cctv_observation").to_dict()
    state["last_result"] = packet
    # Only a known model response releases the resident inference slot. An
    # uncertain transport result propagates above and leaves admission stalled.
    acknowledge_caption(block.store.run_dir, block.run_id, batch["batch_id"], status="error" if state["last_error"] else "ok")
    publication = publish_files(block, writes) if writes else None
    return {"state": state, "outputs": {"published_files": publication} if publication else {},
        "emissions": [{"port": "observed", "value": {"observation": packet}}], "events": events}
