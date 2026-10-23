from __future__ import annotations

import importlib
import json
from pathlib import Path
import sys

import pytest
from mn_blueprint_blocks.event_processing import scope
from mn_blueprint_blocks.context import BlockContext
from mn_blueprint_blocks.testing import BlockHarness
from mn_live_video_analysis_skill import write_frame_batch
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations import block_model_request
from mn_sdk.integrations.block_worker import run
from mn_sdk.integrations.block_publication_files import deliver_files
from mn_sdk.step_runtime import StepContext

ROOT = Path(__file__).resolve().parents[1]
PAYLOADS = ROOT / "cctv_operator/payloads"


def _load_detector():
    sys.path.insert(0, str(PAYLOADS))
    return importlib.import_module("domain.vision")


def _run_detector(module, monkeypatch, tmp_path, capsys, *, payload, detection,
                  state=None, message=None, config=None, gate=None, review_approved=None):
    # Tests select explicit domain settings while executing the actual compiled
    # binding, event admission, scoped state, effects and publication contracts.
    config = config or {"video_source": {"mode": "stream", "uri": "rtsp://camera.example/unit-test"}}
    count = getattr(module, "_fixture_count", 0) + 1
    module._fixture_count = count
    run_dir = tmp_path / "run"
    harness = BlockHarness(run_dir)
    batch_id = "batch-test" if count == 1 else "batch-test-" + str(count)
    camera = payload.get("camera_id") or "cctv"
    instruction = module.normalize_attention_instruction(payload.get("instruction"))
    revision = int(payload.get("instruction_revision") or 0)
    selected = [{"timestamp": 1.0, "score": .5, "content": b"\xff\xd8jpeg-frame\xff\xd9"}]
    path, batch = write_frame_batch(run_dir, batch_id=batch_id, trigger="on_demand" if instruction else "baseline",
        source={"mode": "stream", "uri": "rtsp://camera.example/unit-test", "name": "rtsp://camera.example/unit-test", "position_seconds": 0},
        instruction=instruction, instruction_revision=revision, candidates=selected, selected=selected,
        schema="otterdesk.cctv_operator.frame_batch.v2", metadata={"camera_id": camera, "command_id": payload.get("command_id", ""),
            "candidate_gate": {"detector": "RF-DETR", "condition": "person", "confirmed": True}})
    incoming = {key: batch[key] for key in ("batch_id", "trigger", "instruction", "instruction_revision", "camera_id", "command_id", "candidate_count", "selected_count")}
    incoming.update(frame_batch_ref=path.relative_to(run_dir).as_posix(), tick_seq=int(payload.get("tick_seq") or (state or {}).get("frames_seen", 0) + 1))
    monkeypatch.setenv("MN_RUN_DIR", str(run_dir))
    monkeypatch.setenv("MN_RUN_ID", "test-run")
    monkeypatch.setenv("SLACK_ALERT_ENABLED", "false")
    monkeypatch.delenv("VIDEO_SOURCE_URI", raising=False)
    monkeypatch.delenv("MOCK_VLM_DETECTION", raising=False)
    evidence = importlib.import_module("domain.frame_evidence")
    producer = harness.context(invocation_id="sample-fixture-" + str(count), config=config, job_id="test-job", run_id="test-run", agent_id="adaptive_frame_sampler")
    incoming["frame_evidence"] = evidence.capture_batch(producer, incoming, max_frames=10)
    package = read_blueprint(ROOT / "cctv_operator")
    resolved = resolve_config(package)
    compiled = compile_blueprint(package, resolved).manifest
    node = next(row for row in compiled["agents"]["nodes"] if row["node_id"] == "visual_detector")
    options = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    descriptor = tmp_path / "native-runtime.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, resolved)))
    environment = {**node["config"]["environment"], "MN_RUN_DIR": str(run_dir), "MN_CONTEXT_FILE": str(tmp_path / "native-context.json"),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor), "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
        "MN_BLOCK_EVENT_PROTOCOL": "mn.block_events/v1", "MN_BLOCK_EVENT_PUBLICATION_PROTOCOL": "mn.published_files/v1"}
    prior = {}
    if state:
        owner = harness.context(invocation_id="seed-state", config=config, job_id="test-job", run_id="test-run", agent_id="visual_detector")
        owner.revision = options["revision"]
        reference = harness.store.commit("seed-state-" + str(count) + ".json", {"version": "mn.block_event_state/v1", "scope": scope(owner), "data": state}, kind="block_event_state")
        prior = {"agent_state": {"version": "mn.block_event_state/v1", "reference": reference.to_dict()}}
    Path(environment["MN_CONTEXT_FILE"]).write_text(json.dumps(prior))
    prompts = []
    def encoder(prompt, frames, *, media_format):
        return [{"type": "text", "text": prompt}, {"type": "video_url", "video_url": {"url": "data:video/mp4;base64,dmlkZW8="}}]
    monkeypatch.setattr(module.vision_model, "model_user_content", encoder)
    def model(*args, **kwargs):
        prompts.append(args[3]["messages"][0]["content"][0]["text"])
        matched = detection.get("detected_target", detection.get("detected")) is True
        value = {"scene_understanding": detection.get("summary", "Sampled scene account"), "risk_predictions": [], "uncertainties": [],
            "goal_event": {"start_frame": 1, "end_frame": 1, "evidence_frame": 1} if matched else None, **detection}
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
    monkeypatch.setattr(block_model_request, "runtime_model_json_request", model)
    schedule = importlib.import_module("domain.caption_schedule")
    monkeypatch.setattr(module, "acknowledge_caption", lambda root, run_id, batch_id, *, status: schedule.complete_caption(root, batch_id, status=status))
    context = StepContext(step_id="detect_visual_targets", job_id="test-job", run_id="test-run", agent_id="visual_detector", config=config,
        environment=environment, message={"envelope": {"message_id": "vision-fixture-" + str(count)}, "body": incoming})
    result = run(context, **options)
    # Model the owner publication boundary after successful event acceptance;
    # separate native transition tests assert the worker never copies early.
    if getattr(result, "publication", None):
        deliver_files(BlockContext(store=harness.store, invocation_id="accepted-owner", revision="test",
            environment={}, agent_id="visual_detector"), result.publication)
    return {"next_state": harness.store.read(result.event_result["next"])["data"], "events": result.events}, prompts


def test_quiet_scene_is_analyzed_without_target_screening(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "entrance"},
        detection={"detected": False, "confidence": .9, "summary": "The aisle remains clear.",
                   "scene_understanding": "A parked cart remains beside the aisle."},
        gate={"condition_met": False, "confidence": .94})
    assert len(prompts) == 1
    observed = output["next_state"]["last_observation"]
    assert observed["scene_understanding"] == "A parked cart remains beside the aisle."
    assert observed["condition_screening"]["mode"] == "person_gated_cosmos"
    assert not any(event["type"] == "human_input_requested" for event in output["events"])


@pytest.mark.parametrize("matched,confidence,understanding,expected", [
    (False, .95, "Both visible workers wear helmets.", False),
    (False, .3, "The person's head is occluded; helmet status is uncertain.", False),
    (True, .9, "A worker on the left has a visibly uncovered head while carrying a box.", True),
])
def test_default_helmet_notices_use_cosmos_understanding_only(monkeypatch, tmp_path, capsys,
                                                             matched, confidence, understanding, expected):
    detector = _load_detector()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 1, "camera_id": "warehouse"},
        detection={"detected_target": matched, "confidence": confidence,
                   "summary": "Helmet review.", "scene_understanding": understanding,
                   "helmet_observations": [{"helmet_status": "not_worn", "head_visible": True,
                       "evidence_frame": 1, "visible_evidence": understanding}] if matched else [],
                   "detection_report": "A visible worker is not wearing a helmet." if matched else "No confirmed helmet violation."})
    notices = [event for event in output["events"] if event["type"] == "human_notice"]
    assert bool(notices) is expected
    assert output["next_state"]["last_observation"]["scene_understanding"] == understanding
    assert "A visible person is not wearing a helmet." in prompts[0]
    assert "occluded, distant or unclear head is uncertain" in prompts[0]
    if expected:
        assert understanding in notices[0]["payload"]["message"]
        assert notices[0]["payload"]["image"]


def test_ungated_batch_is_rejected_before_cosmos_or_memory(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    original = detector.read_batch
    def ungated(*args, **kwargs):
        batch, frames, view = original(*args, **kwargs)
        batch.pop("candidate_gate")
        return batch, frames, view
    monkeypatch.setattr(detector, "read_batch", ungated)
    with pytest.raises(ValueError, match="confirmed RF-DETR person gate"):
        _run_detector(detector, monkeypatch, tmp_path, capsys,
            payload={"tick_seq": 1}, detection={"detected_target": True})
    assert not list((tmp_path / "run").glob("blocks/*/model-responses/*.json"))


def test_uncertain_scene_does_not_block_observation_for_approval(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 2, "camera_id": "entrance"},
        detection={"detected": False, "confidence": .3, "summary": "The aisle is obscured.",
                   "uncertainties": ["Occlusion prevents assessing clearance."]},
        review_approved=False)
    assert len(prompts) == 1
    assert output["next_state"]["last_observation"]["uncertainties"] == ["Occlusion prevents assessing clearance."]
    assert not any(event["type"] == "human_input_requested" for event in output["events"])


def test_cctv_operator_chat_context_answers_what_happened(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, _prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 9, "camera_id": "loading-dock", "instruction": "People entering the loading dock.",
                 "instruction_revision": 1},
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 2,
            "detections": [
                {
                    "label": "person",
                    "category": "person",
                    "color": "blue jacket",
                    "position": "left side of the loading dock",
                    "activity": "walking into view",
                    "confidence": 0.91,
                },
                {
                    "label": "person",
                    "category": "person",
                    "color": "dark hoodie",
                    "position": "center of the loading dock",
                    "activity": "following behind",
                    "confidence": 0.89,
                },
            ],
            "confidence": 0.92,
            "summary": "Two people appeared in the loading dock view.",
            "detection_report": "Two people appeared near the loading dock entrance.",
            "activity_description": "Both people are walking into the monitored area.",
            "risk_level": "medium",
            "visible_subjects": ["person", "person"],
        },
    )

    context = output["next_state"]["conversation_context"]
    assert "frame 9" in context["what_happened"].lower()
    assert "two people appeared near the loading dock entrance" in context["what_happened"].lower()
    assert any(event["type"] == "cctv_operator_frame_observed" for event in output["events"])
    assert output["events"][-1]["type"] == "cctv_operator_detection"
    observed = next(
        event["payload"]
        for event in output["events"]
        if event["type"] == "cctv_operator_frame_observed"
    )
    assert observed["frame_batch_ref"] == (
        "frame_batches/batch-test/batch.json"
    )
    assert observed["batch_id"] == "batch-test"
    assert observed["selected_count"] == 1
    assert observed["model_latency_ms"] >= 0
    assert observed["observed_at"].endswith("Z")


def test_monitoring_goal_match_emits_timed_chat_notice_with_frame(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    previous_state = detector.initial_state()
    previous_state["last_observation"] = {
        "frame_seq": 4,
        "camera_id": "front-door",
        "detected_target": False,
        "detection_count": 0,
        "person_like_count": 0,
        "risk_level": "low",
    }

    output, _prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 5, "camera_id": "front-door", "instruction": "People entering the front door.", "instruction_revision": 1},
        state=previous_state,
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 2,
            "detections": [
                {
                    "label": "person",
                    "category": "person",
                    "color": "white shirt",
                    "position": "near the front door",
                    "activity": "standing at the entrance",
                    "confidence": 0.94,
                },
                {
                    "label": "person",
                    "category": "person",
                    "color": "black jacket",
                    "position": "behind the first person",
                    "activity": "entering the frame",
                    "confidence": 0.9,
                },
            ],
            "confidence": 0.94,
            "summary": "Two people appeared at the entrance.",
            "detection_report": "Two people are visible near the front door.",
            "activity_description": "One person is standing while another enters the frame.",
            "risk_level": "medium",
            "visible_subjects": ["person", "person"],
        },
    )

    notice = next(event for event in output["events"] if event["type"] == "human_notice")
    assert notice["payload"]["kind"] == "configured_target_detection"
    assert notice["payload"]["chat_delivery"] == "otterdesk_worker_chat"
    assert notice["payload"]["title"] == "Monitoring goal detected"
    assert "two people" in notice["payload"]["message"].lower()
    assert "front door" in notice["payload"]["message"].lower()
    assert notice["payload"]["observed_at"] == "1970-01-01T00:00:01Z"
    assert "1970-01-01T00:00:01Z" in notice["payload"]["message"]
    assert notice["payload"]["image"]["mime_type"] == "image/jpeg"
    assert notice["payload"]["image"]["run_id"] == "test-run"
    assert notice["payload"]["monitoring_goal"] == "People entering the front door."
    assert not (tmp_path / "run/web/conversation_media.json").exists()


def test_continuing_goal_match_is_not_repeated_after_cooldown(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {**detector.initial_state(), "notified_goal": "A visible person is not wearing a helmet."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3}, state=state,
        detection={"detected_target": True, "confidence": .95, "summary": "The worker still has an uncovered head.",
                   "helmet_observations": [{"helmet_status": "not_worn", "head_visible": True,
                       "evidence_frame": 1, "visible_evidence": "The worker has an uncovered head."}]})
    assert not any(event["type"] == "human_notice" for event in output["events"])
    assert output["next_state"]["notified_goal"] == state["notified_goal"]


def test_unconfirmed_helmet_claim_does_not_rearm_or_notify(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {**detector.initial_state(), "notified_goal": "A visible person is not wearing a helmet."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3}, state=state,
        detection={"detected_target": True, "confidence": .95, "summary": "A person is visible."})
    assert not any(event["type"] == "human_notice" for event in output["events"])
    assert output["next_state"]["notified_goal"] == state["notified_goal"]


def test_confirmed_goal_absence_rearms_notifications(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {**detector.initial_state(), "notified_goal": "A visible person is not wearing a helmet."}
    output, _ = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3}, state=state,
        detection={"detected_target": False, "confidence": .95, "summary": "The group dispersed."})
    assert output["next_state"]["notified_goal"] is None


@pytest.mark.parametrize("matched,confidence,cooldown", [(False, .95, 0), (True, .3, 0), (True, .95, 120)])
def test_unrelated_low_confidence_and_repeated_activity_stay_quiet(monkeypatch, tmp_path, capsys, matched, confidence, cooldown):
    detector = _load_detector()
    state = detector.initial_state()
    state["last_alert_wall_ts"] = __import__("time").time() if cooldown else 0
    output, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 2}, state=state,
        detection={"detected_target": matched, "confidence": confidence,
                   "detections": [{"label": "person", "category": "person"}],
                   "summary": "People are visible.", "scene_understanding": "People are visible."})
    assert "A visible person is not wearing a helmet." in prompts[0]
    assert not any(event["type"] == "human_notice" for event in output["events"])
    assert not (tmp_path / "run/web/conversation_media.json").exists()


def test_cctv_operator_user_attention_request_changes_prompt_and_state(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    output, prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={
            "tick_seq": 3,
            "camera_id": "warehouse-aisle",
            "instruction": "Pay attention to the red backpack near the left doorway.",
            "instruction_revision": 1,
        },
        detection={
            "detected": False,
            "detected_target": False,
            "detection_count": 0,
            "detections": [],
            "confidence": 0.2,
            "summary": "No configured targets are visible yet.",
            "risk_level": "low",
            "visible_subjects": [],
        },
    )

    assert prompts and "red backpack near the left doorway" in prompts[0]
    assert output["next_state"]["attention_instruction"] == "Pay attention to the red backpack near the left doorway."
    assert output["next_state"]["conversation_context"]["attention_instruction"] == (
        "Pay attention to the red backpack near the left doorway."
    )
    attention_event = next(event for event in output["events"] if event["type"] == "cctv_operator_attention_updated")
    assert "red backpack" in attention_event["payload"]["summary"]
    assert output["events"][-1]["type"] == "cctv_operator_frame_observed"


def test_new_person_goal_not_blocked_by_previous_alert_cooldown(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = detector.initial_state()
    state["last_alert_wall_ts"] = __import__("time").time()
    output, _ = _run_detector(
        detector, monkeypatch, tmp_path, capsys,
        payload={"tick_seq": 3, "camera_id": "entrance", "instruction": "Find a person", "instruction_revision": 1},
        state=state,
        detection={
            "detected": True, "detected_target": True, "detection_count": 1,
            "detections": [{"label": "person", "category": "person", "confidence": 0.93}],
            "confidence": 0.93, "summary": "A person is visible.",
            "detection_report": "A person is visible at the entrance.",
            "visible_subjects": ["person"], "risk_level": "low",
        },
    )
    notices = [event for event in output["events"] if event["type"] == "human_notice"]
    assert len(notices) == 1
    assert "person" in notices[0]["payload"]["message"].lower()


def test_cctv_operator_uses_configured_targets_and_notice_policy(
    monkeypatch, tmp_path, capsys
):
    detector = _load_detector()
    output, prompts = _run_detector(
        detector,
        monkeypatch,
        tmp_path,
        capsys,
        payload={"tick_seq": 2, "camera_id": "lobby"},
        config={
            "video_source": {
                "mode": "stream",
                "uri": "rtsp://camera.example/unit-test",
            },
            "inputs": {
                "payload": {
                    "monitoring_goal": "red backpack",
                    "visual_targets": ["red backpack"],
                    "alert_policy": {
                        "mode": "human_notice_only",
                        "min_confidence": 0.8,
                        "cooldown_seconds": 120,
                        "notify_on": ["red backpack"],
                    },
                }
            },
        },
        detection={
            "detected": True,
            "detected_target": True,
            "detection_count": 1,
            "detections": [
                {
                    "label": "red backpack",
                    "category": "unattended package",
                    "color": "red",
                    "position": "left side",
                    "activity": "stationary",
                    "confidence": 0.93,
                }
            ],
            "confidence": 0.93,
            "summary": "A red backpack is visible in the lobby.",
            "detection_report": "A red backpack is stationary on the left.",
            "risk_level": "medium",
            "visible_subjects": ["red backpack"],
        },
    )

    assert "red backpack" in prompts[0].lower()
    detection_event = next(
        event
        for event in output["events"]
        if event["type"] == "cctv_operator_detection"
    )
    assert detection_event["payload"]["configured_targets"] == [
        "red backpack"
    ]
    assert detection_event["payload"]["alert_decision"]["notify"] is True
    notice = next(
        event for event in output["events"] if event["type"] == "human_notice"
    )
    assert notice["payload"]["kind"] == "configured_target_detection"
    assert notice["payload"]["matched_targets"] == ["red backpack"]
    assert not any(
        str(event["type"]).startswith("cctv_operator_slack_alert_")
        for event in output["events"]
    )


def test_cctv_operator_batch_revision_can_clear_attention_state(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    state = {
        **detector.initial_state(),
        "attention_instruction": "Watch the red backpack.",
        "attention_targets": ["Watch the red backpack."],
        "instruction_revision": 1,
    }

    result, _ = _run_detector(detector, monkeypatch, tmp_path, capsys, state=state,
        payload={"instruction": "", "instruction_revision": 2}, detection={"detected_target": False})
    state = result["next_state"]
    event = next(event for event in result["events"] if event["type"] == "cctv_operator_attention_updated")

    assert state["attention_instruction"] == ""
    assert state["attention_targets"] == []
    assert state["instruction_revision"] == 2
    assert event["payload"]["cleared"] is True


def test_cctv_setup_offers_sample_and_secure_external_source():
    ui = json.loads((ROOT / "cctv_operator/extensions/ui.json").read_text())
    guide = ui["setup_guide"]
    assert guide["sample"]["available"] is True
    assert guide["sample"]["values"]["video_source.profile"] == "bundled_demo"
    assert guide["real"]["values"]["video_source.profile"] == "external"
    fields = {field["path"]: field for field in guide["fields"]}
    stream = fields["video_source.uri"]
    assert stream["secret"] is True
    assert stream["required"] is True
    assert stream["active_when_any"] == [{"key": "video_source.profile", "equals": "external"}]
    assert set(stream["protocols"]) == {"rtsp:", "rtsps:", "rtmp:", "rtmps:"}
    assert all(not field["required"] for key, field in fields.items()
               if key not in {"video_source.profile", "video_source.uri", "video_source.demo_file", "inputs.payload.monitoring_goal"})


def test_floor_focus_replaces_default_targets_in_model_request(monkeypatch, tmp_path, capsys):
    detector = _load_detector()
    instruction = "can you focus on find foreign object on the floor?"
    monkeypatch.setenv("VISUAL_DETECTION_TARGETS", "person, vehicle")
    output, prompts = _run_detector(
        detector, monkeypatch, tmp_path, capsys,
        payload={"instruction": instruction, "instruction_revision": 2,
                 "command_id": "floor-focus"},
        detection={"detected": False, "detected_target": False,
                   "detections": [], "detection_count": 0, "confidence": 0.8,
                   "summary": "No foreign object is visible on the floor.",
                   "risk_level": "low"},
    )
    targets = prompts[0].split("## Targets\n", 1)[1].split("## Current analysis goal", 1)[0]
    assert targets.strip() == instruction
    assert "person, vehicle" not in prompts[0]
    assert output["next_state"]["attention_instruction"] == instruction
    assert output["next_state"]["instruction_revision"] == 2
    restored, prompts = _run_detector(detector, monkeypatch, tmp_path, capsys, state=output["next_state"],
        payload={"instruction": "", "instruction_revision": 3}, detection={"detected_target": False})
    assert restored["next_state"]["attention_instruction"] == ""
    assert "A visible person is not wearing a helmet." in prompts[0]


def test_chat_planner_receives_steering_semantics_from_normalized_contract(tmp_path):
    from mn_sdk_common.response_service import normalize_response_service
    from mn_sdk_job_response.agent_planner import AgentPlanner
    from mn_sdk_job_response.agent_memory import AgentMemory
    from mn_sdk_job_response.agent_store import AgentStore

    source = json.loads((ROOT / "cctv_operator/extensions/response.json").read_text())
    source.pop("$schema")
    from mn_sdk.blueprints import read_blueprint, blueprint_definition
    declaration = blueprint_definition(read_blueprint(ROOT / "cctv_operator"))["response_service"]["agent"]
    store = AgentStore(tmp_path / "conversation.sqlite3", "cctv-test")
    memory = AgentMemory(declaration=declaration, store=store,
                         job_data_dir=tmp_path, rag_refresh=lambda: None)
    planner = AgentPlanner(declaration=declaration, store=store, memory=memory)
    question = "can you focus on find foreign object on the floor?"
    prompt = json.loads(planner.user_prompt(question, {}, [], ""))
    tools = prompt["allowed_user_tools"]
    assert question in tools["set_monitoring_instruction"]["description"]
    assert "change the goal to watch the corridor" in tools["set_monitoring_instruction"]["description"]
    assert declaration["activity"]["tool"] == "watch_job_activity"
    assert "watch_job_activity" not in tools
    assert 'Never use "latest"' in tools["get_operator_activity"]["description"]
    assert "command_id" not in tools["set_monitoring_instruction"]["arguments"]
    assert "action" in prompt["turn_contract"]["allowed_intents"]
    plan = planner.validate_plan({
        "intent": "action", "tool": "set_monitoring_instruction",
        "arguments": {"instruction": question, "clear": False, "analyze_now": True},
    }, question)
    assert plan["arguments"]["instruction"] == question
    assert plan["arguments"]["command_id"]
