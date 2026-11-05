"""Mac computer use through the real blocks, memory and conversation contracts."""
import base64
import copy
import importlib
import io
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config
from mn_sdk_common.committed_artifacts import CommittedJsonStore

from blueprint_modernization_support import assert_modular_payload, assert_registry_handlers_import

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "general_assistant"
TASK = "Using Gmail, send the email I specified. Ask me to sign in if necessary."


@pytest.fixture
def conversation_events(monkeypatch):
    from mn_sdk.blueprint import approvals as human_interactions
    events = []
    monkeypatch.setattr(human_interactions, "publish_human_interaction_event",
                        lambda run, kind, payload: events.append({"type": kind, "payload": payload, "run_id": run}))
    monkeypatch.setattr(human_interactions, "await_human_decision", lambda run, identity, **kwargs: {
        "type": "human_input_received", "payload": {"request_id": identity, "notes": "I signed in. Continue.", "decision": "respond"}})
    return events


@pytest.fixture
def domain(monkeypatch, conversation_events):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    modules = SimpleNamespace(**{name: importlib.import_module("domain." + name)
        for name in ["intake", "solver", "engine", "reporting", "memory", "configuration", "conversation", "visual_memory"]})
    monkeypatch.setattr(modules.configuration, "require_mac", lambda: None)
    monkeypatch.setattr(modules.visual_memory, "RuntimeEmbeddings", MemoryEmbeddings)
    return modules


class MemoryEmbeddings:
    metadata = {"model": "test-embeddinggemma2", "tokenizer": "test-image-space"}

    def __init__(self, model="embeddinggemma-2", **kwargs):
        self.model, self.images, self.queries = model, [], []

    def embed_media(self, media):
        self.images.append(media)
        return {"vector": [1., 0.], **self.metadata}

    def embed_query(self, media):
        self.queries.append(media)
        return {"vector": [1., 0.], **self.metadata}


def visual_owner(domain, tmp_path, *, run="run-one", job="job-one", config=None):
    block = context(tmp_path, step="solve_task", run=run, job=job, config=config)
    return domain.visual_memory.VisualMemory(block)


def visual_request(owner):
    return {"job_id": owner.block.job_id, "run_id": owner.block.run_id, "admitted_at": 1700000000}


def context(tmp_path, *, job="job-one", run="run-one", step="prepare_task", config=None):
    config = copy.deepcopy(config or resolve_config(read_blueprint(BLUEPRINT)).data)
    return BlockContext(store=CommittedJsonStore(tmp_path / run), invocation_id=run + ":" + step,
        revision="general_assistant@3.0.0", config=config, max_calls=256,
        job_id=job, run_id=run, step_id=step, job_data_dir=str(tmp_path / job), environment={})


class Desktop:
    def __init__(self, *, permissions=True, failure=None):
        self.permissions, self.failure = permissions, failure
        self.calls, self.actions = [], []
        self.suspended = False
        self.closed = False
        self.frames = 0
        self.controls = [{"control_id": f"c{index}", "role": "AXTextField" if index == 1 else "AXButton", "label": f"Test control {index}", "editable": index == 1}
                         for index in range(1, 4)]

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.closed = True

    def request(self, action):
        self.calls.append(action)
        kind = action["type"]
        if kind == "status":
            return {"bundle_id": "io.mirrorneuron.computer-use", "accessibility": self.permissions,
                    "screen_recording": self.permissions, "stopped": self.failure == "stopped"}
        if kind == "suspend":
            self.suspended = True
        elif kind == "resume":
            self.suspended = False
            self.permissions = True
        elif kind == "observe":
            assert not self.suspended
            self.frames += 1
            return {"frame_id": str(self.frames), "bundle_id": "com.apple.Safari", "width": 1200, "height": 800,
                    "mime_type": "image/jpeg", "image_base64": base64.b64encode(b"synthetic screenshot").decode(),
                    "controls": self.controls, "text_field_focused": True}
        elif kind not in {"request_permissions", "quit"}:
            assert not self.suspended
            assert action["frame_id"] == str(self.frames)
            self.actions.append(action)
            if self.failure:
                raise self.failure
            return {"performed": True, "type": kind}
        return {}


def model_actions(monkeypatch, domain, desktop, actions):
    requests = []
    queue = iter(actions)
    monkeypatch.setattr(domain.engine, "ComputerSession", lambda: desktop)
    def respond(block, request, **kwargs):
        requests.append(request)
        assert request["model"] == request["payload"]["model"] == "vision"
        assert request["options"]["required_capabilities"] == ["image_input", "structured_output"]
        value = {"action": next(queue)}
        __import__("jsonschema").validate(value, request["payload"]["response_format"]["json_schema"]["schema"])
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(value)}}]}
    monkeypatch.setattr(domain.engine, "model_request", respond)
    return requests


DONE = {"type": "done", "summary": "The requested message was sent.", "evidence": "Gmail shows Message sent."}


def execute(domain, tmp_path, *, config=None, run="run-one", job="job-one"):
    prepare = context(tmp_path, config=config, run=run, job=job)
    admitted = domain.intake.prepare(prepare, {"task": TASK})
    solver = context(tmp_path, config=config, run=run, job=job, step="solve_task")
    solved = domain.solver.solve(solver, {"previous": admitted})
    published = domain.reporting.publish(context(tmp_path, config=config, run=run, job=job, step="publish_task"), {"previous": solved})
    return prepare.store, admitted, solved, published


def test_native_local_mac_24gb_default_model_and_memory_contract():
    package = read_blueprint(BLUEPRINT)
    compiled = compile_blueprint(package).manifest
    assert package.manifest["name"] == "Computer Use"
    assert package.manifest["version"] == "3.0.0"
    assert "general_assistant" in json.loads((ROOT / "index.json").read_text())
    execution = package.document("execution")
    assert execution["requirements"]["os"] == "darwin"
    assert execution["requirements"]["memory"] == {"min_gb": 24}
    assert execution["runtime"]["placement"]["must_run_local"] is True
    assert {"MN_LLM_PROVIDER", "MN_LLM_API_BASE", "MN_COMPUTER_USE_APP"} <= set(execution["defaults"]["worker"]["with"]["pass_env"])
    llm = package.extension("mn.llm")
    assert llm["model"] == "vision" and "provider" not in llm
    assert llm["required_capabilities"] == ["image_input", "structured_output"]
    assert package.extension("mn.context")["text_memory"]["enabled"] is True
    nodes = compiled["agents"]["nodes"]
    assert not any(n.get("config", {}).get("runner_module") == "MirrorNeuron.Runner.OpenShell" for n in nodes)
    solve = next(n for n in nodes if n["node_id"] == "solve_task__block_solve_task_specialist")["config"]
    assert solve["safe_to_retry"] is False and solve["max_attempts"] == 1
    # The real native host rejects a longer invocation before any worker starts.
    assert 0 < solve["timeout_seconds"] <= 3600
    assert solve["environment"]["MN_WORKFLOW_STEP_HANDLER"] == "mn_sdk.integrations.block_worker"
    assert {s["name"] for s in package.document("dependencies")["skills"]} == {"mirrorneuron-computer-use-skill"}
    from mn_sdk.version_constraints import version_satisfies
    skill = package.document("dependencies")["skills"][0]
    assert skill["setup"] == "on_install"
    assert not version_satisfies("1.4.1.dev7", skill["version"])
    assert version_satisfies("1.4.1.dev8", skill["version"])
    assert version_satisfies("1.4.1", skill["version"])
    assert not version_satisfies("2.0.0", skill["version"])
    config = resolve_config(package).data
    assert config["inputs"]["payload"]["task"] == ""
    assert "input_folder" not in config["inputs"]["payload"] and "local_inputs" not in config
    assert config["outputs"]["folder_path"] == "~/Documents/computer-use"
    assert config["computer_use"]["walltime_seconds"] < solve["timeout_seconds"]
    assert not package.extension("mn.ui")["setup_guide"]["sample"]["available"]
    assert_modular_payload("general_assistant")
    assert_registry_handlers_import("general_assistant")


@pytest.mark.parametrize("memory_gb", [23, 24])
@pytest.mark.parametrize("os_name", ["darwin", "linux", "windows"])
def test_memory_and_os_admission(memory_gb, os_name):
    from mn_sdk.workflow_placement import node_rejections, workflow_node_requirements
    from mn_sdk.model_runtime import resolve_model_entry
    requirements = workflow_node_requirements(blueprint_definition(read_blueprint(BLUEPRINT)),
        runtime_model_requirements=[], model_entry_resolver=resolve_model_entry)
    assert requirements["min_host_memory_mb"] == 24576
    node = {"name": "test-node", "hardware": {"platform": {"os": os_name},
        "cpu": {"logical_processors": 8}, "memory": {"total_mb": memory_gb * 1024},
        "disk": {"available_mb": 65536}, "gpu": {"available": False}}}
    reasons = node_rejections("test-node", resource=node, system=node, requirements=requirements, explicit_node="")
    assert any(reason.startswith("host_memory_total_mb=") for reason in reasons) == (memory_gb < 24)
    assert any(reason.startswith("operating_system_requires=") for reason in reasons) == (os_name != "darwin")


def test_empty_task_asks_in_chat_and_freezes_real_reply(domain, tmp_path, conversation_events):
    block = context(tmp_path)
    admitted = domain.intake.prepare(block, {})
    request = block.store.read(admitted["request"])["data"]
    assert request["task"] == "I signed in. Continue."
    assert "memory" not in request and "gateway" not in request and "attachments" not in request
    assert conversation_events[0]["type"] == "human_input_requested"
    assert domain.intake.prepare(block, {"task": "different"}) == admitted
    assert len(conversation_events) == 1


@pytest.mark.parametrize("task", [1, "x" * 64001])
def test_invalid_task_fails_before_control(domain, tmp_path, task):
    with pytest.raises(ValueError, match="task"):
        domain.intake.prepare(context(tmp_path), {"task": task})


@pytest.mark.parametrize("key", ["MN_BLUEPRINT_FAKE_LLM", "MN_BLUEPRINT_FAKE_SKILLS"])
def test_fake_execution_cannot_open_the_real_desktop(domain, monkeypatch, tmp_path, key):
    block = context(tmp_path)
    block.environment = {key: "1"}
    monkeypatch.setattr(domain.engine, "ComputerSession", lambda: pytest.fail("Must not control a real desktop in fake mode"))
    with pytest.raises(ValueError, match="disabled when fake"):
        domain.intake.prepare(block, {"task": TASK})


@pytest.mark.parametrize("permissions", [True, False])
def test_gmail_help_suspends_then_observes_and_completes_once(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events, permissions):
    desktop = Desktop(permissions=permissions)
    requests = model_actions(monkeypatch, domain, desktop, [
        {"type": "ask_user", "question": "Please open Gmail and sign in, then reply when ready."},
        {"type": "key", "key": "cmd+l"},
        {"type": "type_text", "control_id": "c1", "text": "synthetic confidential message"}, DONE])
    real_wait = domain.conversation.human_interactions.await_human_decision
    def wait(*args, **kwargs):
        assert desktop.suspended
        before = desktop.frames
        value = real_wait(*args, **kwargs)
        assert desktop.frames == before
        return value
    monkeypatch.setattr(domain.conversation.human_interactions, "await_human_decision", wait)
    store, admitted, solved, published = execute(domain, tmp_path)
    assert published["status"] == "completed"
    assert desktop.closed and len(desktop.actions) == 2
    assert desktop.frames == len(requests) == 4
    assert sum(e["type"] == "human_input_requested" for e in conversation_events) == (1 if permissions else 2)
    result = store.read_path("result.json")
    assert result["memory"]["navigation_records_retained"] == 1
    assert result["requires_reconciliation"] is False
    assert "synthetic confidential" not in json.dumps(store.read_path("computer-use-audit.json"))
    assert "Gmail shows Message sent" in store.read_bytes(published["artifacts"]["answer"]).decode()
    # Completed block replay cannot open a helper, call a model, or send again.
    assert domain.solver.solve(context(tmp_path, step="solve_task"), {"previous": admitted}) == solved
    assert len(desktop.actions) == 2 and len(requests) == 4
    from mn_sdk.integrations.block_publication_files import deliver_files, verified_files
    block = context(tmp_path, step="publish_task")
    exported = verified_files(block, published["published_files"])
    assert {"result.json", "answer.md", "computer-use-audit.json"} <= set(exported)
    assert not any("private" in name or ".jpg" in name for name in exported)
    block.environment = {"MN_JOB_OUTPUT_DIR": str(tmp_path / "delivered")}
    deliver_files(block, published["published_files"])
    assert (tmp_path / "delivered/answer.md").is_file()


def test_default_system_provider_is_used_for_vision(domain, monkeypatch, tmp_path):
    block = context(tmp_path, step="solve_task")
    block.environment = {"MN_LLM_PROVIDER": "litellm"}
    request = {"task": TASK, "supervisor_instructions": [], "settings": block.config["computer_use"]}
    desktop = Desktop()
    requests = model_actions(monkeypatch, domain, desktop, [DONE])
    domain.engine.decide(block, request, desktop.request({"type": "observe"}), {}, [], 0, 60)
    assert requests[0]["options"]["provider"] == "litellm"
    assert "api_key" not in json.dumps(requests)


def test_screen_request_uses_the_provider_base_without_duplicating_its_version(domain, monkeypatch, tmp_path):
    from mn_sdk.model_access import runtime
    from urllib.parse import urlsplit

    block = context(tmp_path, step="solve_task")
    request = {"task": TASK, "supervisor_instructions": [], "settings": block.config["computer_use"]}
    calls = []
    def prepare(purpose, model, *args, **kwargs):
        assert purpose == "llm" and model == "vision"
        assert kwargs["required_capabilities"] == ["image_input", "structured_output"]
        return runtime.RuntimeModelBinding(purpose="llm", logical_model="vision", catalog_id="vision",
            model="vision", runtime_model="vision", api_model="vision", provider="litellm",
            api_base="https://provider.invalid/v1")
    def send(http_request, **kwargs):
        assert urlsplit(http_request.full_url).path == "/v1/chat/completions"
        payload = json.loads(http_request.data)
        assert payload["model"] == "vision"
        image = payload["messages"][1]["content"][1]["image_url"]["url"]
        assert image == "data:image/jpeg;base64," + base64.b64encode(b"synthetic screenshot").decode()
        calls.append(payload)
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop",
            "message": {"content": json.dumps({"action": DONE})}}]}).encode())
    monkeypatch.setattr(runtime, "ensure_runtime_model", prepare)
    monkeypatch.setattr(runtime.urllib.request, "urlopen", send)
    assert domain.engine.decide(block, request, Desktop().request({"type": "observe"}), {}, [], 0, 60) == DONE
    assert len(calls) == 1


def test_safe_provider_error_is_published_without_dispatching_desktop_input(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [])
    def unavailable(*args, **kwargs):
        raise domain.engine.RuntimeModelError("Runtime model request failed with HTTP 404.")
    monkeypatch.setattr(domain.engine, "model_request", unavailable)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "failed" and desktop.closed and not desktop.actions
    answer = store.read_bytes(published["artifacts"]["answer"]).decode()
    assert "Runtime model request failed with HTTP 404." in answer
    assert store.read_path("result.json")["requires_reconciliation"] is False


def test_named_controls_use_a_fresh_frame_and_are_not_navigation_memory(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    desktop.controls = [{"control_id": "c1", "role": "AXButton", "label": "Compose", "editable": False}]
    requests = model_actions(monkeypatch, domain, desktop, [{"type": "activate_control", "control_id": "c1"}, DONE])
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed"
    content = json.loads(requests[0]["payload"]["messages"][1]["content"][0]["text"])
    assert content["visible_controls"] == desktop.controls
    assert desktop.actions == [{"type": "activate_control", "control_id": "c1", "frame_id": "1"}]
    assert store.read_path("result.json")["memory"]["navigation_records_retained"] == 0
    assert "control_id" not in json.dumps(store.read_path("computer-use-audit.json"))


def test_model_cannot_activate_a_control_omitted_from_its_observation(domain, monkeypatch, tmp_path):
    desktop = Desktop()
    desktop.controls = [{"control_id": "c1", "role": "AXButton", "label": "Compose", "editable": False},
                        {"control_id": "c2", "role": "AXButton", "label": "", "editable": False}]
    def ignore_schema(*args, **kwargs):
        return {"choices": [{"message": {"content": json.dumps({"action": {"type": "activate_control", "control_id": "c2"}})}}]}
    monkeypatch.setattr(domain.engine, "model_request", ignore_schema)
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="not available in this observation"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
            "settings": block.config["computer_use"]}, desktop.request({"type": "observe"}), {}, [], 0, 60)
    assert not desktop.actions


@pytest.mark.parametrize("bundle", [False, 0, "Chrome browser", "x" * 201])
def test_invalid_app_scope_is_rejected_before_desktop_work(domain, tmp_path, bundle):
    from jsonschema import ValidationError
    with pytest.raises(ValidationError):
        domain.intake.prepare(context(tmp_path), {"task": TASK, "target_app_bundle_id": bundle})


def test_admitted_app_scope_is_frozen_with_the_task(domain, tmp_path):
    block = context(tmp_path)
    admitted = domain.intake.prepare(block, {"task": TASK, "target_app_bundle_id": "com.google.Chrome"})
    assert block.store.read(admitted["request"])["data"]["target_app_bundle_id"] == "com.google.Chrome"
    assert domain.intake.prepare(block, {"task": "Changed", "target_app_bundle_id": "com.apple.Safari"}) == admitted


@pytest.mark.parametrize("action", [
    {"type": "activate_control", "control_id": "c1"},
    {"type": "type_text", "control_id": "c1", "text": "Keep this out of the wrong app"},
    {"type": "key", "key": "return"},
    {"type": "open_url", "url": "https://mail.google.com"},
    {"type": "launch_app", "bundle_id": "com.apple.Safari"},
    DONE,
])
def test_app_scope_prevents_input_or_completion_in_another_app(domain, monkeypatch, tmp_path, action):
    desktop = Desktop()
    def ignore_schema(block, request, **kwargs):
        variants = request["payload"]["response_format"]["json_schema"]["schema"]["properties"]["action"]["anyOf"]
        offered = {v["properties"]["type"]["enum"][0]: v for v in variants}
        assert set(offered) == {"launch_app", "wait", "ask_user"}
        assert offered["launch_app"]["properties"]["bundle_id"]["enum"] == ["com.google.Chrome"]
        return {"choices": [{"message": {"content": json.dumps({"action": action})}}]}
    monkeypatch.setattr(domain.engine, "model_request", ignore_schema)
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="outside this run's app scope"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
            "target_app_bundle_id": "com.google.Chrome", "settings": block.config["computer_use"]},
            desktop.request({"type": "observe"}), {}, [], 0, 60)
    assert not desktop.actions


def test_app_scope_allows_controls_after_activating_the_target_app(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    original = desktop.request
    def observe_target(action):
        result = original(action)
        if action["type"] == "observe" and desktop.actions:
            result["bundle_id"] = "com.google.Chrome"
        return result
    monkeypatch.setattr(desktop, "request", observe_target)
    requests = model_actions(monkeypatch, domain, desktop, [
        {"type": "activate_control", "control_id": "c1"}, DONE])
    config = resolve_config(read_blueprint(BLUEPRINT), overrides={
        "inputs": {"payload": {"target_app_bundle_id": "com.google.Chrome"}}}).data
    _, _, _, result = execute(domain, tmp_path, config=config)
    assert result["status"] == "completed"
    assert [a["type"] for a in desktop.actions] == ["launch_app", "activate_control"]
    assert json.loads(requests[0]["payload"]["messages"][1]["content"])["target_app_bundle_id"] == "com.google.Chrome"
    offered = requests[0]["payload"]["response_format"]["json_schema"]["schema"]["properties"]["action"]["anyOf"]
    kinds = {value["properties"]["type"]["enum"][0] for value in offered}
    assert not {"open_url", "launch_app"} & kinds


def test_model_cannot_reactivate_an_already_scoped_app(domain, monkeypatch, tmp_path):
    desktop = Desktop()
    monkeypatch.setattr(domain.engine, "model_request", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps({
            "action": {"type": "launch_app", "bundle_id": "com.apple.Safari"}})}}]})
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="outside this run's app scope"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
            "target_app_bundle_id": "com.apple.Safari", "settings": block.config["computer_use"]},
            desktop.request({"type": "observe"}), {}, [], 0, 60)
    assert not desktop.actions


def scoped_focus_desktop(domain, monkeypatch, *, always_interrupt=False):
    desktop = Desktop()
    request = desktop.request
    active = False
    interrupted = False
    def focused_request(action):
        nonlocal active, interrupted
        if action["type"] == "activate_control" and (always_interrupt or not interrupted):
            interrupted, active = True, False
            raise domain.engine.ComputerUseError("stale_frame", "Another app took focus; no input was performed.")
        result = request(action)
        if action["type"] == "launch_app":
            active = True
        elif action["type"] == "observe" and active:
            result["bundle_id"] = "com.google.Chrome"
        return result
    monkeypatch.setattr(desktop, "request", focused_request)
    return desktop


def test_scoped_app_can_be_restored_after_verified_foreground_loss(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = scoped_focus_desktop(domain, monkeypatch)
    model_actions(monkeypatch, domain, desktop, [
        {"type": "activate_control", "control_id": "c1"},
        {"type": "activate_control", "control_id": "c1"}, DONE])
    config = resolve_config(read_blueprint(BLUEPRINT), overrides={
        "inputs": {"payload": {"target_app_bundle_id": "com.google.Chrome"}}}).data
    store, _, _, result = execute(domain, tmp_path, config=config)
    assert result["status"] == "completed"
    assert [action["type"] for action in desktop.actions] == ["launch_app", "launch_app", "activate_control"]
    audit = store.read_path("computer-use-audit.json")
    assert audit["questions"] == 0
    assert sum(a["outcome"] == "stale_frame" and a["performed"] is False for a in audit["actions"]) == 1


def test_repeated_foreground_loss_pauses_before_a_fourth_restore(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = scoped_focus_desktop(domain, monkeypatch, always_interrupt=True)
    model_actions(monkeypatch, domain, desktop, [{"type": "activate_control", "control_id": "c1"}] * 3)
    questions = []
    def unanswered(self, identity, question, **kwargs):
        questions.append(question)
        raise TimeoutError("No actual human reply")
    monkeypatch.setattr(domain.engine.Conversation, "ask", unanswered)
    config = resolve_config(read_blueprint(BLUEPRINT), overrides={
        "inputs": {"payload": {"target_app_bundle_id": "com.google.Chrome"}}}).data
    store, _, _, result = execute(domain, tmp_path, config=config)
    assert result["status"] == "failed" and desktop.suspended
    assert len(desktop.actions) == 3 and all(a["type"] == "launch_app" for a in desktop.actions)
    assert questions == ["Another app keeps taking focus. Please leave the target app in front while I work, then reply when ready."]
    assert store.read_path("computer-use-audit.json")["actions"][-1]["outcome"] == "focus_interrupted"


def test_actual_help_reply_is_present_as_a_user_message(domain, monkeypatch, tmp_path):
    captured = []
    def respond(block, request, **kwargs):
        captured.append(request)
        return {"choices": [{"message": {"content": json.dumps({"action": DONE})}}]}
    monkeypatch.setattr(domain.engine, "model_request", respond)
    block = context(tmp_path, step="solve_task")
    domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
        "settings": block.config["computer_use"]}, Desktop().request({"type": "observe"}), {},
        [{"question": "Is Gmail ready?", "user_reply": "Ready; Gmail and Compose are fully visible"}], 1, 60)
    messages = captured[0]["payload"]["messages"]
    assert any(m["role"] == "user" and m["content"] ==
        "Supervisor reply to that question: Ready; Gmail and Compose are fully visible" for m in messages)
    assert messages[-1]["content"][-1]["type"] == "image_url"


def test_answered_help_is_not_requested_again_without_progress(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events):
    desktop = Desktop()
    question = {"type": "ask_user", "question": "Is Gmail ready?"}
    model_actions(monkeypatch, domain, desktop, [question, question])
    store, _, _, result = execute(domain, tmp_path)
    assert result["status"] == "failed" and not desktop.actions
    assert sum(e["type"] == "human_input_requested" for e in conversation_events) == 1
    assert store.read_path("computer-use-audit.json")["failure"]["stage"] == "conversation_progress"


def test_typing_is_not_offered_or_accepted_without_an_editable_target(domain, monkeypatch, tmp_path):
    desktop = Desktop()
    frame = desktop.request({"type": "observe"})
    frame["text_field_focused"] = False
    frame["controls"] = [dict(c, editable=False) for c in frame["controls"]]
    def ignore_schema(block, request, **kwargs):
        variants = request["payload"]["response_format"]["json_schema"]["schema"]["properties"]["action"]["anyOf"]
        assert "type_text" not in {value["properties"]["type"]["enum"][0] for value in variants}
        return {"choices": [{"message": {"content": json.dumps({"action": {"type": "type_text", "control_id": "c1", "text": "Do not type"}})}}]}
    monkeypatch.setattr(domain.engine, "model_request", ignore_schema)
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="not editable in this observation"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
            "settings": block.config["computer_use"]}, frame, {}, [], 0, 60)
    assert not desktop.actions


@pytest.mark.parametrize("target", ["c2", "c99"])
def test_typing_rejects_noneditable_or_stale_control_ids(domain, monkeypatch, tmp_path, target):
    desktop = Desktop()
    monkeypatch.setattr(domain.engine, "model_request", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps({
            "action": {"type": "type_text", "control_id": target, "text": "test"}})}}]})
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="not editable in this observation"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
            "settings": block.config["computer_use"]}, desktop.request({"type": "observe"}), {}, [], 0, 60)
    assert not desktop.actions


def test_targeted_typing_is_offered_before_the_target_has_focus(domain, monkeypatch, tmp_path):
    desktop = Desktop()
    frame = desktop.request({"type": "observe"})
    frame["text_field_focused"] = False
    action = {"type": "type_text", "control_id": "c1", "text": "test"}
    model_actions(monkeypatch, domain, desktop, [action])
    block = context(tmp_path, step="solve_task")
    assert domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [],
        "settings": block.config["computer_use"]}, frame, {}, [], 0, 60) == action


def test_send_is_followed_by_observation_only_verification(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    desktop.controls[1]["label"] = "Send (⌘Enter)"
    requests = model_actions(monkeypatch, domain, desktop, [{"type": "activate_control", "control_id": "c2"}, DONE])
    store, _, _, result = execute(domain, tmp_path)
    assert result["status"] == "completed" and len(desktop.actions) == 1
    variants = requests[-1]["payload"]["response_format"]["json_schema"]["schema"]["properties"]["action"]["anyOf"]
    assert {v["properties"]["type"]["enum"][0] for v in variants} == {"wait", "ask_user", "done"}
    assert store.read_path("computer-use-audit.json")["actions"][0]["commit_check"] is True


def test_another_input_cannot_bypass_commit_verification(domain, monkeypatch, tmp_path):
    monkeypatch.setattr(domain.engine, "model_request", lambda *args, **kwargs: {
        "choices": [{"message": {"content": json.dumps({"action": {"type": "type_text", "control_id": "c1", "text": "Send"}})}}]})
    block = context(tmp_path, step="solve_task")
    with pytest.raises(ValueError, match="blocked while checking"):
        domain.engine.decide(block, {"task": TASK, "supervisor_instructions": [], "verify_commit": True,
            "settings": block.config["computer_use"]}, Desktop().request({"type": "observe"}), {}, [], 0, 60)


def test_rejected_typing_is_not_replayed_before_the_model_focuses_a_field(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    requests = model_actions(monkeypatch, domain, desktop, [
        {"type": "type_text", "control_id": "c1", "text": "test recipient"},
        {"type": "activate_control", "control_id": "c1"},
        {"type": "type_text", "control_id": "c1", "text": "test recipient"}, DONE])
    request = desktop.request
    focused = False
    def focus_required(action):
        nonlocal focused
        if action["type"] == "type_text" and not focused:
            raise domain.engine.ComputerUseError("text_field_required", "Focus the intended text field before typing. No text was entered.")
        if action["type"] == "activate_control":
            focused = True
        return request(action)
    monkeypatch.setattr(desktop, "request", focus_required)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and len(requests) == 4
    assert [action["type"] for action in desktop.actions] == ["activate_control", "type_text"]
    assert store.read_path("computer-use-audit.json")["actions"][0]["performed"] is False


@pytest.mark.parametrize("source_context", [True, False])
@pytest.mark.parametrize("override_task", [None, "Read the existing window. Do not send an email."])
def test_deployed_block_bindings_accept_task_and_publish_without_exporting_screens(domain, monkeypatch, tmp_path, text_memory_transport, source_context, override_task):
    from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
    from mn_sdk.integrations.block_worker import run
    from mn_sdk.step_runtime import StepContext
    package = read_blueprint(BLUEPRINT)
    config = resolve_config(package, overrides={"inputs": {"payload": {"task": TASK}},
                                              "source_context": {"enabled": source_context}})
    compiled = compile_blueprint(package, config).manifest
    bindings = package.extension("mn.blocks")["steps"]["prepare_task"]["inputs"]
    assert bindings == {field: {"$ref": "run_input", "path": [field]}
                        for field in ["task", "target_app_bundle_id", "supervisor_instructions"]}
    descriptor = tmp_path / "worker-manifest.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
    environment = {"MN_RUN_DIR": str(tmp_path / "run"), "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
                   "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    desktop = Desktop()
    requests = model_actions(monkeypatch, domain, desktop, [{"type": "key", "key": "cmd+l"}, DONE])
    previous = None
    for step_id in ["prepare_task", "solve_task", "publish_task"]:
        node = next(n for n in compiled["agents"]["nodes"] if n["node_id"] == f"{step_id}__block_{step_id}_specialist")
        parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
        step = StepContext(step_id=step_id, agent_id=node["node_id"], run_id="run-one", job_id="job-one",
            idempotency_key="run-one/" + step_id, config=config.data, environment=environment,
            job_data_dir=str(tmp_path / "job"), message={"body": {"step_input": {"previous": previous} if previous else {"task": override_task}}})
        output = run(step, **parameters)
        previous = output.outputs["result"]
    store = CommittedJsonStore(tmp_path / "run")
    published = store.read(previous)
    assert published["status"] == "completed" and len(desktop.actions) == 1
    received = json.loads(requests[0]["payload"]["messages"][1]["content"][0]["text"])
    assert received["task"] == (override_task or TASK)
    assert store.read_path("result.json")["memory"]["status"] == "updated"
    from mn_sdk.integrations.block_publication_files import verified_files
    files = verified_files(context(tmp_path, run="run", step="publish_task", config=config.data), published["published_files"])
    assert any(name.startswith("context_sources/") for name in files) is source_context
    assert not any("private" in name or name.endswith(".jpg") for name in files)


def test_navigation_memory_recall_is_job_private_and_omits_sensitive_content(domain, tmp_path, text_memory_transport):
    block = context(tmp_path)
    memory = domain.memory.NavigationMemory(block)
    request = {"request_id": "request-one", "admitted_at": 1700000000}
    actions = [{"type": "open_url", "url": "https://mail.google.com/mail/u/0/?token=synthetic-secret#inbox"},
               {"type": "type_text", "control_id": "c1", "text": "alice@example.com and secret email body"},
               {"type": "click", "x": .2, "y": .3}, {"type": "key", "key": "cmd+l"}]
    hints = [hint for action in actions if (hint := domain.memory.navigation_hint(action))]
    receipts = memory.remember(request, {"com.apple.Safari": hints})
    assert memory.remember(request, {"com.apple.Safari": hints})
    assert receipts
    memory.close()
    later = domain.memory.NavigationMemory(context(tmp_path, run="run-two"))
    packet, receipt = later.recall("com.apple.Safari")
    assert "cmd+l" in json.dumps(packet) and "mail.google.com" in json.dumps(packet)
    assert all(text not in json.dumps(packet) for text in ["synthetic-secret", "alice@example.com", "secret email body", "/mail/u/0", "#inbox"])
    empty, _ = later.recall("com.apple.Notes")
    assert not empty["evidence"]
    other = domain.memory.NavigationMemory(context(tmp_path, job="job-two"))
    isolated, _ = other.recall("com.apple.Safari")
    assert not isolated["evidence"]


def test_first_navigation_query_has_a_schema_and_does_not_recall_the_declaration(domain, tmp_path, text_memory_transport):
    memory = domain.memory.NavigationMemory(context(tmp_path))
    retrieve = memory.session.client.retrieve
    def schema_checked(request):
        records = text_memory_transport.scopes.get(("job-one", None), {})
        columns = set()
        for text in records.values():
            lines = text.splitlines()
            header = lines[lines.index("## Facts") + 2]
            columns.update(value.strip() for value in header.strip("|").split("|"))
        analytical = request["stages"][0]["analytical"]
        needed = {analytical["timestamp_field"], *(value["field"] for value in analytical["filters"])}
        if not needed <= columns:
            raise ValueError("analytical field unavailable in Markdown structure")
        return retrieve(request)
    memory.session.client.retrieve = schema_checked
    packet, _ = memory.recall("com.apple.Safari")
    assert packet["evidence"] == []
    memory.close()


@pytest.mark.parametrize("failure,unknown", [(OSError("synthetic disconnect"), True),
    ("unknown_outcome", True), ("stopped", False)])
def test_unknown_or_stopped_native_action_never_repeats_or_learns(domain, monkeypatch, tmp_path, text_memory_transport, failure, unknown):
    if isinstance(failure, str) and failure != "stopped":
        failure = domain.engine.ComputerUseError(failure, "Inspect the desktop before retrying")
    desktop = Desktop(failure=failure)
    model_actions(monkeypatch, domain, desktop, [{"type": "activate_control", "control_id": "c1"}, DONE])
    store, admitted, solved, published = execute(domain, tmp_path)
    assert published["status"] == "failed" and desktop.closed
    assert store.read_path("result.json")["requires_reconciliation"] is unknown
    assert len(desktop.actions) == (0 if failure == "stopped" else 1)
    assert store.read_path("result.json")["memory"]["navigation_records_retained"] == 0
    # The authored query schema is allowed; failed work adds no navigation.
    records = text_memory_transport.scopes.get(("job-one", None), {})
    assert all("computer_navigation_schema" in text for text in records.values())


def test_interrupted_session_is_fenced_before_reopening_helper(domain, monkeypatch, tmp_path):
    block = context(tmp_path)
    admitted = domain.intake.prepare(block, {"task": TASK})
    solver = context(tmp_path, step="solve_task")
    solver.store.commit(solver.root + "/private/desktop-started.json", {"request_id": "already-started"})
    monkeypatch.setattr(domain.engine, "ComputerSession", lambda: pytest.fail("Must not reopen a fenced session"))
    with pytest.raises(RuntimeError, match="reconciliation"):
        domain.solver.solve(solver, {"previous": admitted})


def test_stale_screen_is_reobserved_before_a_new_decision(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    requests = model_actions(monkeypatch, domain, desktop, [
        {"type": "activate_control", "control_id": "c1"}, {"type": "key", "key": "cmd+l"}, DONE])
    request = desktop.request
    def stale_once(action):
        if action["type"] == "activate_control":
            raise domain.engine.ComputerUseError("stale_frame", "Observe again")
        return request(action)
    monkeypatch.setattr(desktop, "request", stale_once)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and desktop.frames == len(requests) == 3
    assert [action["type"] for action in desktop.actions] == ["key"]
    assert store.read_path("computer-use-audit.json")["actions"][0]["performed"] is False


def test_unchanged_screen_suspends_control_and_asks_for_help(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events):
    desktop = Desktop()
    requests = model_actions(monkeypatch, domain, desktop, [
        {"type": "activate_control", "control_id": "c1"}, {"type": "activate_control", "control_id": "c2"},
        {"type": "activate_control", "control_id": "c3"}, DONE])
    real_wait = domain.conversation.human_interactions.await_human_decision
    def wait(*args, **kwargs):
        assert desktop.suspended and len(desktop.actions) == 3
        return real_wait(*args, **kwargs)
    monkeypatch.setattr(domain.conversation.human_interactions, "await_human_decision", wait)
    _, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and len(desktop.actions) == 3
    assert len(requests) == 4 and desktop.frames == 5
    assert sum(event["type"] == "human_input_requested" for event in conversation_events) == 1


def changing_screens(monkeypatch, desktop):
    request = desktop.request
    def changing(action):
        result = request(action)
        if action["type"] == "observe":
            result["image_base64"] = base64.b64encode(f"synthetic changing screen {desktop.frames}".encode()).decode()
        return result
    monkeypatch.setattr(desktop, "request", changing)


@pytest.mark.parametrize("navigation", [{"type": "open_url", "url": "https://mail.google.com"},
                                      {"type": "launch_app", "bundle_id": "com.google.Chrome"}])
def test_repeated_navigation_pauses_before_a_second_effect_even_when_screens_change(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events, navigation):
    desktop = Desktop()
    changing_screens(monkeypatch, desktop)
    model_actions(monkeypatch, domain, desktop, [navigation, navigation, DONE])
    real_wait = domain.conversation.human_interactions.await_human_decision
    def wait(*args, **kwargs):
        assert desktop.suspended and len(desktop.actions) == 1
        return real_wait(*args, **kwargs)
    monkeypatch.setattr(domain.conversation.human_interactions, "await_human_decision", wait)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and len(desktop.actions) == 1
    assert sum(event["type"] == "human_input_requested" for event in conversation_events) == 1
    blocked = store.read_path("computer-use-audit.json")["actions"][1]
    assert blocked["performed"] is False and blocked["outcome"] == "navigation_loop"


def test_waiting_and_changing_tab_bars_do_not_release_the_navigation_guard(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events):
    desktop = Desktop()
    changing_screens(monkeypatch, desktop)
    navigation = {"type": "open_url", "url": "https://mail.google.com"}
    model_actions(monkeypatch, domain, desktop, [navigation, {"type": "wait", "seconds": 1}, navigation, DONE])
    _, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed"
    assert [action["type"] for action in desktop.actions] == ["open_url", "wait"]
    assert sum(event["type"] == "human_input_requested" for event in conversation_events) == 1


def test_observed_control_progress_allows_a_later_navigation_to_the_same_target(domain, monkeypatch, tmp_path, text_memory_transport, conversation_events):
    desktop = Desktop()
    changing_screens(monkeypatch, desktop)
    navigation = {"type": "open_url", "url": "https://mail.google.com"}
    model_actions(monkeypatch, domain, desktop, [navigation, {"type": "activate_control", "control_id": "c1"}, navigation, DONE])
    _, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed"
    assert [action["type"] for action in desktop.actions] == ["open_url", "activate_control", "open_url"]
    assert not any(event["type"] == "human_input_requested" for event in conversation_events)


def test_launching_the_current_app_does_not_reopen_it(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [{"type": "launch_app", "bundle_id": "com.apple.Safari"}, DONE])
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and not desktop.actions
    assert store.read_path("computer-use-audit.json")["actions"][0]["outcome"] == "already_active"


def test_failure_after_input_requires_desktop_reconciliation(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [{"type": "activate_control", "control_id": "c1"}, DONE])
    request = desktop.request
    def disconnected_after_input(action):
        if action["type"] == "observe" and desktop.actions:
            raise OSError("synthetic connection lost after input delivery")
        return request(action)
    monkeypatch.setattr(desktop, "request", disconnected_after_input)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "failed" and len(desktop.actions) == 1
    assert store.read_path("result.json")["requires_reconciliation"] is True


def test_memory_write_failure_preserves_the_observed_completed_result(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [{"type": "key", "key": "cmd+l"}, DONE])
    def unavailable(*args, **kwargs):
        raise RuntimeError("Synthetic memory service failure")
    monkeypatch.setattr(domain.memory.NavigationMemory, "remember", unavailable)
    store, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "completed" and len(desktop.actions) == 1
    result = store.read_path("result.json")
    assert result["memory"]["status"] == "write_failed"
    assert not result["requires_reconciliation"]
    answer = store.read_bytes(published["artifacts"]["answer"]).decode()
    assert "Gmail shows Message sent" in answer and "memory could not be updated" in answer


def test_expired_exact_reply_cannot_resume_control(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [{"type": "ask_user", "question": "Please sign in"}, DONE])
    clock = [1700000000.0]
    monkeypatch.setattr(domain.conversation.time, "time", lambda: clock[0])
    def late(run, identity, **kwargs):
        clock[0] += 601
        return {"type": "human_input_received", "payload": {"request_id": identity, "notes": "Ready"}}
    monkeypatch.setattr(domain.conversation.human_interactions, "await_human_decision", late)
    _, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "failed"
    assert not any(action["type"] == "resume" for action in desktop.calls)


@pytest.mark.parametrize("event", [
    {"type": "human_input_timeout", "payload": {}},
    {"type": "human_input_received", "payload": {"request_id": "foreign", "notes": "Invented"}},
])
def test_missing_or_foreign_reply_cannot_resume_control(domain, monkeypatch, tmp_path, text_memory_transport, event):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [{"type": "ask_user", "question": "Please sign in"}, DONE])
    monkeypatch.setattr(domain.conversation.human_interactions, "await_human_decision", lambda *a, **kw: event)
    _, _, _, published = execute(domain, tmp_path)
    assert published["status"] == "failed" and desktop.closed
    assert not any(call["type"] == "resume" for call in desktop.calls)
    assert not desktop.actions


@pytest.mark.parametrize("value", [
    {"type": "click", "x": True, "y": 0}, {"type": "click", "x": 2, "y": 0},
    {"type": "scroll", "x": .5, "y": .5, "amount": 1.5}, {"type": "shell", "command": "anything"},
    {"type": "type_text", "control_id": "c1", "text": "x", "extra": "bad"}, {"type": "key", "key": "cmd+exec"},
    {"type": "open_url", "url": "file:///etc/passwd"}, {"type": "open_url", "url": "https://u:p@example.com"},
    {"type": "done", "summary": "Done", "evidence": ""},
    {"type": "activate_control", "control_id": "foreign"},
    {"type": "wait", "seconds": False}, {"type": "wait", "seconds": 0},
])
def test_malformed_model_tools_fail_before_native_dispatch(domain, value):
    with pytest.raises(ValueError):
        domain.engine.action_value({"choices": [{"message": {"content": json.dumps({"action": value})}}]})


def test_supervisor_rules_are_frozen_and_forgetting_affects_next_run(domain, tmp_path):
    rule = {"id": "check-first", "kind": "work_rule", "text": "Explain observed checks."}
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["inputs"]["payload"].update(task=TASK, supervisor_instructions=[rule])
    block = context(tmp_path, config=config)
    admitted = domain.intake.prepare(block, {})
    config["inputs"]["payload"]["supervisor_instructions"] = []
    assert domain.intake.prepare(block, {}) == admitted
    assert block.store.read(admitted["request"])["data"]["supervisor_instructions"] == [rule]
    later = context(tmp_path, config=config, run="run-two")
    second = domain.intake.prepare(later, {})
    assert later.store.read(second["request"])["data"]["supervisor_instructions"] == []


@pytest.mark.parametrize("rules", ["not an array", [{"id": "bad", "kind": "action", "text": "Start"}],
    [{"id": "same", "kind": "communication", "text": "Short"}] * 2])
def test_invalid_saved_rules_fail_before_model_work(domain, tmp_path, rules):
    with pytest.raises((ValueError, __import__("jsonschema").ValidationError)):
        domain.intake.prepare(context(tmp_path), {"task": TASK, "supervisor_instructions": rules})


def test_visual_memory_indexes_original_images_and_recalls_across_runs(domain, tmp_path, text_memory_transport):
    from mn_context_engine_sdk import MediaInput
    first = visual_owner(domain, tmp_path)
    frame = Desktop().request({"type": "observe"})
    first.capture(frame, {"type": "type_text", "control_id": "c1", "text": "must-not-store-this"})
    result = first.remember(visual_request(first), completed=True)
    assert result["images_learned"] == 1 and first.embeddings.model == "embeddinggemma-2"
    assert first.embeddings.images == [MediaInput(b"synthetic screenshot", "image/jpeg")]
    assert "control_id" not in first.store.path.read_text() and "must-not-store-this" not in first.store.path.read_text()
    first.close()
    later = visual_owner(domain, tmp_path, run="run-two")
    packet, receipt = later.recall(frame)
    assert packet["status"] == "ready"
    assert packet["matches"][0]["field_hints"] == [{"role": "AXTextField", "label": "Test control 1"}]
    assert packet["matches"][0]["source_run_id"] == "run-one"
    assert later.embeddings.queries == [MediaInput(b"synthetic screenshot", "image/jpeg")]
    assert not later.embeddings.images and not receipt["reused_layout_query"]
    later.recall({**frame, "image_base64": base64.b64encode(b"changed text in the same UI layout").decode()})
    assert len(later.embeddings.queries) == 1
    assert "control_id" not in json.dumps(packet) and "must-not-store-this" not in json.dumps(packet)
    later.close()


def test_visual_memory_never_crosses_job_or_app_boundaries(domain, tmp_path, text_memory_transport):
    first = visual_owner(domain, tmp_path)
    frame = Desktop().request({"type": "observe"})
    first.capture(frame)
    first.remember(visual_request(first), completed=True)
    first.close()
    other = visual_owner(domain, tmp_path, run="run-two", job="job-other")
    assert other.recall(frame)[0]["status"] == "empty"
    assert not other.embeddings.queries
    other.close()
    later = visual_owner(domain, tmp_path, run="run-two")
    assert later.recall({**frame, "bundle_id": "com.google.Chrome"})[0]["status"] == "empty"
    later.close()
    forged = context(tmp_path, job="job-other", run="run-three")
    forged.job_data_dir = str(tmp_path / "job-one")
    with pytest.raises(ValueError, match="another Job"):
        domain.visual_memory.VisualMemory(forged)


@pytest.mark.parametrize("changed_time,accepted", [(1793580491.52766, True), (1793580492.52766, False)])
def test_visual_provenance_uses_transport_stable_observation_time(
        domain, tmp_path, text_memory_transport, monkeypatch, changed_time, accepted):
    owner = visual_owner(domain, tmp_path)
    frame = {**Desktop().request({"type": "observe"}), "observed_at": 1793580491.5276601}
    owner.capture(frame)
    assert next(iter(owner.states.values()))["observed_at"] == 1793580491.528
    owner.remember(visual_request(owner), completed=True)
    read_complete = owner.session.client.read_complete

    def transported(*args, **kwargs):
        source = copy.deepcopy(read_complete(*args, **kwargs))
        for value in source["metadata"]["upstream"]:
            if "computer_use_visual" in value:
                value["observed_at"] = changed_time
        return source

    monkeypatch.setattr(owner.session.client, "read_complete", transported)
    if accepted:
        assert owner.recall(frame)[0]["status"] == "ready"
    else:
        with pytest.raises(ValueError, match="canonical provenance"):
            owner.recall(frame)
        assert not owner.embeddings.queries
    owner.close()


@pytest.mark.parametrize("change", ["targets", "run_id", "scope", "image"])
def test_visual_locators_and_pixels_are_checked_against_canonical_sources(domain, tmp_path, text_memory_transport, change):
    owner = visual_owner(domain, tmp_path)
    frame = Desktop().request({"type": "observe"})
    owner.capture(frame)
    owner.remember(visual_request(owner), completed=True)
    value = json.loads(owner.store.path.read_text())
    row = value["entries"][0]
    if change == "targets":
        row["targets"] = [{"role": "AXTextField", "label": "forged navigation"}]
    elif change == "run_id":
        row["run_id"] = "another-run"
    elif change == "scope":
        row["catalog"]["scope"][0] = "another-corpus"
    else:
        (owner.store.root / "images" / (row["media"]["sha256"] + ".jpg")).write_bytes(b"tampered")
    owner.store.path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        owner.recall(frame)
    assert not owner.embeddings.queries
    owner.close()


def test_visual_index_failure_is_pending_and_recoverable_without_desktop_replay(domain, tmp_path, text_memory_transport):
    owner = visual_owner(domain, tmp_path)
    frame = Desktop().request({"type": "observe"})
    owner.capture(frame)
    def unavailable(_media):
        raise RuntimeError("embedding service unavailable")
    owner.embeddings.embed_media = unavailable
    with pytest.raises(RuntimeError, match="embedding service"):
        owner.remember(visual_request(owner), completed=True)
    assert owner.store.entries()[0]["model_identity"] is None
    owner.close()
    later = visual_owner(domain, tmp_path, run="run-two")
    assert later.recall(frame)[0]["status"] == "ready"
    assert len(later.embeddings.images) == 1
    later.close()


def test_visual_memory_capacity_is_explicit_and_does_not_delete_prior_images(domain, tmp_path, text_memory_transport):
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["visual_memory"]["max_images"] = 1
    owner = visual_owner(domain, tmp_path, config=config)
    frame = Desktop().request({"type": "observe"})
    owner.capture(frame)
    owner.capture({**frame, "bundle_id": "com.google.Chrome", "image_base64": base64.b64encode(b"other pixels").decode()})
    result = owner.remember(visual_request(owner), completed=True)
    assert result["status"] == "capacity_reached" and result["states_skipped"] == 1
    assert len(owner.store.entries()) == len(list((owner.store.root / "images").glob("*.jpg"))) == 1
    owner.close()


def test_failed_tasks_do_not_publish_buffered_visual_lessons(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [
        {"type": "type_text", "control_id": "c1", "text": "synthetic text"},
        {"type": "open_url", "url": "http://not-allowed.example"}])
    _, _, _, result = execute(domain, tmp_path)
    assert result["status"] == "failed"
    assert not list((tmp_path / "job-one").rglob("*.jpg"))
    owner = visual_owner(domain, tmp_path, run="run-two")
    assert not owner.store.entries()
    with pytest.raises(ValueError, match="Only completed"):
        owner.remember(visual_request(owner), completed=False)
    owner.close()


def test_visual_write_failure_preserves_a_completed_task(domain, monkeypatch, tmp_path, text_memory_transport):
    desktop = Desktop()
    model_actions(monkeypatch, domain, desktop, [DONE])
    def unavailable(*args, **kwargs):
        raise RuntimeError("embedding service unavailable")
    monkeypatch.setattr(domain.visual_memory.VisualMemory, "remember", unavailable)
    store, _, _, result = execute(domain, tmp_path)
    assert result["status"] == "completed"
    assert store.read_path("result.json")["memory"]["visual"]["status"] == "write_failed"
