"""General Assistant contracts and real Harness2 recursion with deterministic sessions."""
import copy
import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_blueprint_blocks.context import BlockContext
from mn_sdk.blueprints import blueprint_definition, compile_blueprint, read_blueprint, resolve_config
from mn_sdk_common.committed_artifacts import CommittedJsonStore

from blueprint_modernization_support import assert_modular_payload, assert_registry_handlers_import

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / "general_assistant"


@pytest.fixture(autouse=True)
def conversation_events(monkeypatch):
    from mn_sdk import human_interactions
    events = []
    def publish(run, kind, payload):
        events.append({"type": kind, "payload": payload, "run_id": run})
    def reply(run, identity, **kwargs):
        return {"type": "human_input_received", "payload": {
            "request_id": identity, "notes": "Convert the Java code to Rust", "decision": "respond"}}
    monkeypatch.setattr(human_interactions, "publish_human_interaction_event", publish)
    monkeypatch.setattr(human_interactions, "await_human_decision", reply)
    return events


@pytest.fixture
def domain(monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT / "payloads"))
    return SimpleNamespace(**{name: importlib.import_module("domain." + name)
                             for name in ["intake", "solver", "reporting", "memory", "configuration"]})


def context(tmp_path, *, job="job-one", run="run-one", step="prepare_task", config=None):
    config = copy.deepcopy(config or resolve_config(read_blueprint(BLUEPRINT)).data)
    if not config["inputs"]["payload"].get("input_folder"):
        folder = tmp_path / "configured-input"
        folder.mkdir(exist_ok=True)
        (folder / "notes.md").write_text("# Supporting notes\nSynthetic task material.")
        config["inputs"]["payload"]["input_folder"] = str(folder)
    return BlockContext(store=CommittedJsonStore(tmp_path / run), invocation_id=run + ":" + step,
        revision="general_assistant@2.0.0", config=config,
        job_id=job, run_id=run, step_id=step, job_data_dir=str(tmp_path / job))


def test_catalog_default_model_memory_and_openshell_boundary():
    package = read_blueprint(BLUEPRINT)
    compiled = compile_blueprint(package).manifest
    assert "general_assistant" in json.loads((ROOT / "index.json").read_text())
    requirements = package.document("execution")["requirements"]
    assert requirements["memory"] == {"min_gb": 32}
    assert requirements["gpu"] == {"min_count": 0}
    assert package.extension("mn.llm")["model"] == "default"
    assert resolve_config(package).data["text_memory"]["enabled"] is False
    selected = [node for node in compiled["agents"]["nodes"]
                if node.get("config", {}).get("runner_module") == "MirrorNeuron.Runner.OpenShell"]
    assert len(selected) == 1
    config = selected[0]["config"]
    assert config["environment"]["MN_WORKFLOW_STEP_HANDLER"] == "mn_sdk.integrations.block_worker"
    assert config["artifact_handoff"]["version"] == "mn.artifact_handoff/v1"
    assert not config.get("sync_shared_storage")
    fields = package.extension("mn.ui")["init_config_review"]["fields"]
    assert [field["path"] for field in fields] == ["inputs.payload.input_folder", "outputs.folder_path"]
    assert "task" not in resolve_config(package).data["inputs"]["payload"]
    assert config["pass_env"] == ["MN_GRPC_AUTH_TOKEN", "MN_LLM_API_KEY"]
    assert_modular_payload("general_assistant")
    assert_registry_handlers_import("general_assistant")


@pytest.mark.parametrize("vendor", ["apple", "nvidia", None])
@pytest.mark.parametrize("memory_gb", [31, 32])
def test_32gb_admission_is_independent_of_gpu(vendor, memory_gb):
    from mn_sdk.model_runtime import resolve_model_entry
    from mn_sdk.workflow_placement import node_rejections, workflow_node_requirements
    requirements = workflow_node_requirements(blueprint_definition(read_blueprint(BLUEPRINT)),
        runtime_model_requirements=[], model_entry_resolver=resolve_model_entry)
    assert requirements["min_host_memory_mb"] == 32768
    assert requirements["min_gpu_count"] == requirements["min_gpu_memory_mb"] == 0
    node = {"name": "test-node", "hardware": {
        "cpu": {"logical_processors": 8}, "memory": {"total_mb": memory_gb * 1024},
        "disk": {"available_mb": 65536},
        "gpu": {"available": vendor is not None, "vendor": vendor, "memory_total_mb": 1024},
    }}
    reasons = node_rejections("test-node", resource=node, system=node,
                              requirements=requirements, explicit_node="")
    assert any(reason.startswith("host_memory_total_mb=") for reason in reasons) == (memory_gb < 32)
    assert not any(reason.startswith(("gpu_", "gpu:")) for reason in reasons)


def test_admission_is_private_immutable_and_replayable(domain, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "work.txt").write_text("original")
    (source / ".env").write_text("synthetic secret excluded")
    block = context(tmp_path)
    first = domain.intake.prepare(block, {"task": "Improve this file", "input_folder": str(source)})
    (source / "work.txt").write_text("later changes")
    assert domain.intake.prepare(block, {"task": "Improve this file", "input_folder": str(source)}) == first
    admitted = block.store.read(first["request"])["data"]
    assert set(admitted["attachments"]) == {"work.txt"}
    assert block.store.read_bytes(admitted["attachments"]["work.txt"]) == b"original"
    assert admitted["gateway"]["model"] == "default"
    assert "api_key" not in json.dumps(admitted)


def test_task_is_typed_in_conversation_and_markdown_is_readable(domain, tmp_path, conversation_events):
    block = context(tmp_path)
    admitted = domain.intake.prepare(block, {})
    request = block.store.read(admitted["request"])["data"]
    assert request["task"] == "Convert the Java code to Rust"
    assert "notes.md" in request["attachments"]
    assert conversation_events[0]["type"] == "human_input_requested"
    assert conversation_events[0]["payload"]["blocking"] is True
    assert domain.intake.prepare(block, {}) == admitted
    assert len(conversation_events) == 1


def test_compiled_workers_receive_task_in_chat_and_publish_output(domain, monkeypatch, tmp_path, conversation_events):
    pytest.importorskip("harness2")
    from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
    from mn_sdk.integrations.block_worker import run
    from mn_sdk.step_runtime import StepContext
    package = read_blueprint(BLUEPRINT)
    source = tmp_path / "input"
    source.mkdir()
    (source / "notes.md").write_text("# Synthetic Markdown material")
    config = resolve_config(package, overrides={"inputs": {"payload": {"input_folder": str(source)}}})
    compiled = compile_blueprint(package, config).manifest
    descriptor = tmp_path / "worker-manifest.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, config)))
    node = next(node for node in compiled["agents"]["nodes"]
                if node["node_id"] == "prepare_task__block_prepare_task_specialist")
    parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
    environment = {"MN_RUN_DIR": str(tmp_path / "run"),
                   "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
                   "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    step = StepContext(step_id="prepare_task", agent_id=node["node_id"], run_id="run-one", job_id="job-one",
        idempotency_key="run-one/prepare_task", config=config.data, environment=environment,
        job_data_dir=str(tmp_path / "job"), message={"body": {"step_input": {"task": None}}})
    result = run(step, **parameters)
    store = CommittedJsonStore(tmp_path / "run")
    prepared = store.read(result.outputs["result"])
    request = store.read(prepared["request"])["data"]
    assert request["task"] == "Convert the Java code to Rust"
    assert set(request["attachments"]) == {"notes.md"}
    assert conversation_events[0]["type"] == "human_input_requested"
    engine = importlib.import_module("domain.engine")
    monkeypatch.setattr(engine, "run_opencode", SimulatedModel())
    monkeypatch.setattr(domain.solver, "require_openshell", lambda: None)
    for step_id in ["solve_task", "publish_task"]:
        node = next(node for node in compiled["agents"]["nodes"]
                    if node["node_id"] == f"{step_id}__block_{step_id}_specialist")
        parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
        step = StepContext(step_id=step_id, agent_id=node["node_id"], run_id="run-one", job_id="job-one",
            idempotency_key="run-one/" + step_id, config=config.data, environment=environment,
            job_data_dir=str(tmp_path / "job"), message={"body": {"step_input": {"previous": result.outputs["result"]}}})
        result = run(step, **parameters)
    published = store.read(result.outputs["result"])
    assert published["status"] == "completed"
    assert store.read_path("result.json")["deliverables"]
    assert (source / "notes.md").read_text() == "# Synthetic Markdown material"
    assert any(event["payload"].get("message", "").startswith("Your results are ready")
               for event in conversation_events)


@pytest.mark.parametrize("bad_task", ["", " ", 1, "x" * 64001])
def test_invalid_task_fails_before_model_work(domain, tmp_path, bad_task):
    with pytest.raises(ValueError, match="task"):
        domain.intake.prepare(context(tmp_path), {"task": bad_task})


def test_source_symlink_and_input_quota_fail(domain, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "linked").symlink_to(tmp_path / "outside")
    with pytest.raises(ValueError, match="symlink"):
        domain.intake.prepare(context(tmp_path), {"task": "Read files", "input_folder": str(source)})
    (source / "linked").unlink()
    (source / "file.txt").write_text("longer than one byte")
    block = context(tmp_path, run="quota")
    block.config["harness"]["max_input_bytes"] = 1
    with pytest.raises(ValueError, match="quota"):
        domain.intake.prepare(block, {"task": "Read files", "input_folder": str(source)})


def test_memory_generation_replay_conflicts_and_job_isolation(domain, tmp_path):
    block = context(tmp_path)
    limits = domain.configuration.settings(block)
    initial = domain.memory.load(block, limits)
    updated = {**initial, "files": {"active/LongTermMEMORY.md": "A retained lesson"},
               "generation": 1, "last_request": "request-one"}
    first = domain.memory.adopt(block, updated, expected_generation=0, request_id="request-one", limits=limits)
    assert domain.memory.adopt(block, updated, expected_generation=0, request_id="request-one", limits=limits) == first
    assert domain.memory.load(block, limits)["generation"] == 1
    stale = {**updated, "last_request": "stale"}
    with pytest.raises(ValueError, match="changed since admission"):
        domain.memory.adopt(block, stale, expected_generation=0, request_id="stale", limits=limits)
    other = context(tmp_path, job="job-two")
    assert domain.memory.load(other, limits)["files"] == {}
    with pytest.raises(ValueError, match="Job identity"):
        domain.memory.validate(updated, limits, other.job_id)
    with pytest.raises(ValueError, match="relative"):
        domain.memory.validate({**updated, "files": {"../escape": "bad"}}, limits, block.job_id)


class SimulatedModel:
    """Only the external CLI session is simulated; upstream orchestration is real."""
    def __init__(self, *, fail=False):
        self.calls = 0
        self.fail = fail
        self.models = []

    def __call__(self, request, **kwargs):
        self.calls += 1
        self.models.append((request.model, request.gateway.model))
        if self.fail:
            raise RuntimeError("Synthetic provider failure")
        folder = Path(request.folder)
        if (folder / "MISSION.md").is_file():
            harness = folder / "context/harness/systemprompt.md"
            if harness.is_file():
                harness.write_text(harness.read_text() + "\nVerify arithmetic with Python.\n")
            text = ("<notes>Check arithmetic using observed tool output.</notes>\n"
                    "<edits>component: systemprompt.md\nchange: add arithmetic verification\n"
                    "observed: the probe executed the check\nverdict: helped</edits>\n"
                    "<experience>\ncue: When arithmetic is required\n"
                    "lesson: Verify arithmetic with Python before publishing.\n"
                    "evidence: The probe's calculation was present in its tool output.\n"
                    "confidence: limited to the observed task\n</experience>")
        else:
            (folder / "output/answer.md").write_text("# Result\nThe checked answer is 42.\n")
            (folder / "output/data.txt").write_text("42\n")
            assert folder / "input" not in request.writable_paths
            assert folder not in request.writable_paths
            assert request.writable_paths[0] == folder / "output"
            if (folder / "input/work.txt").exists():
                (folder / "output/work.txt").write_text("fixed\n")
            text = "The checked answer is 42."
        return SimpleNamespace(text=text, events=[{"type": "text", "part": {"text": text}}], usage=[])


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_real_harness2_recursion_persists_context_and_replays(domain, monkeypatch, tmp_path, mode):
    pytest.importorskip("harness2")
    engine = importlib.import_module("domain.engine")
    fake = SimulatedModel()
    monkeypatch.setattr(engine, "run_opencode", fake)
    monkeypatch.setattr(domain.solver, "require_openshell", lambda: None)
    source = tmp_path / "source"
    source.mkdir()
    (source / "work.txt").write_text("original")
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["harness"]["mode"] = mode
    prepare = context(tmp_path, config=config)
    admitted = domain.intake.prepare(prepare, {"task": "Check arithmetic and fix work.txt", "input_folder": str(source)})
    solve = context(tmp_path, step="solve_task", config=config)
    owner_target = os.environ.get("MN_GRPC_TARGET")
    solved = domain.solver.solve(solve, {"previous": admitted})
    assert os.environ.get("MN_GRPC_TARGET") == owner_target
    calls = fake.calls
    assert calls >= 8  # Four solver runs, three improver stages and reflection.
    assert all(model == ("mn/default", "default") for model in fake.models)
    assert domain.solver.solve(solve, {"previous": admitted}) == solved
    assert fake.calls == calls
    publish = context(tmp_path, step="publish_task", config=config)
    published = domain.reporting.publish(publish, {"previous": solved})
    assert published["status"] == "completed"
    assert domain.reporting.publish(publish, {"previous": solved}) == published
    assert (source / "work.txt").read_text() == "original"
    assert solve.store.path("deliverables/work.txt").read_text() == "fixed\n"
    public = publish.store.read_path("result.json")
    assert "memory" not in public and public["improvement"]["generation"] == 1
    from mn_sdk.integrations.block_publication_files import deliver_files, verified_files
    exported = verified_files(publish, published["published_files"])
    assert {"result.json", "answer.md", "harness-audit.json"} <= set(exported)
    assert not any("memory" in name or name.startswith("private/") for name in exported)
    publish.environment = {"MN_JOB_OUTPUT_DIR": str(tmp_path / "delivered")}
    deliver_files(publish, published["published_files"])
    assert (tmp_path / "delivered/answer.md").read_text().startswith("# Result")
    assert not (tmp_path / "delivered/private").exists()
    memory = domain.memory.load(publish, domain.configuration.settings(publish))
    assert "Verify arithmetic" in memory["files"]["active/systemprompt.md"]
    assert any(name.endswith("EXPERIENCE.md") for name in memory["files"])
    next_prepare = context(tmp_path, run="run-two", config=config)
    second = domain.intake.prepare(next_prepare, {"task": "Another general task"})
    request = next_prepare.store.read(second["request"])["data"]
    assert request["memory"] == memory
    next_solve = context(tmp_path, run="run-two", step="solve_task", config=config)
    next_result = domain.solver.solve(next_solve, {"previous": second})
    result = next_solve.store.read(next_result["outcome"])["data"]
    audit = next_solve.store.read(result["improvement"])
    assert audit["library_entries_before"] >= 1


def test_real_harness2_failure_preserves_memory(domain, monkeypatch, tmp_path):
    pytest.importorskip("harness2")
    engine = importlib.import_module("domain.engine")
    monkeypatch.setattr(engine, "run_opencode", SimulatedModel(fail=True))
    monkeypatch.setattr(domain.solver, "require_openshell", lambda: None)
    prepare = context(tmp_path)
    admitted = domain.intake.prepare(prepare, {"task": "A task with an unavailable provider"})
    solve = context(tmp_path, step="solve_task")
    solved = domain.solver.solve(solve, {"previous": admitted})
    publish = context(tmp_path, step="publish_task")
    assert domain.reporting.publish(publish, {"previous": solved})["status"] == "failed"
    assert domain.memory.load(publish, domain.configuration.settings(publish))["generation"] == 0
    assert publish.store.read_path("result.json")["improvement"]["memory_retained"] is False


def test_session_allowance_and_host_execution_guard(domain, monkeypatch, tmp_path):
    with pytest.raises((RuntimeError, FileNotFoundError)):
        domain.configuration.require_openshell()
    pytest.importorskip("harness2")
    engine = importlib.import_module("domain.engine")
    block = context(tmp_path)
    values = copy.deepcopy(block.config["harness"])
    values["max_sessions"] = 1
    request = {"settings": values, "gateway": {"api_base": "http://localhost:4000/v1", "model": "default"}}
    sessions = engine.Sessions(block, request)
    monkeypatch.setattr(engine, "run_opencode", lambda _, **kwargs: SimpleNamespace(usage=[]))
    sessions.execute(tmp_path, "one", writable=(tmp_path,))
    with pytest.raises(RuntimeError, match="allowance"):
        sessions.execute(tmp_path, "two", writable=(tmp_path,))


@pytest.mark.parametrize("mode", ["sequential", "parallel"])
def test_solver_question_waits_for_real_conversation_reply(domain, monkeypatch, tmp_path, conversation_events, mode):
    pytest.importorskip("harness2")
    engine = importlib.import_module("domain.engine")
    failures = []
    execute = engine.TaskAdapter.execute
    def observe(*args, **kwargs):
        try:
            return execute(*args, **kwargs)
        except Exception as error:
            failures.append(repr(error))
            raise
    monkeypatch.setattr(engine.TaskAdapter, "execute", observe)
    model = SimulatedModel()
    asked = set()
    def clarify(request, **kwargs):
        folder = Path(request.folder)
        if not (folder / "MISSION.md").exists() and folder not in asked:
            asked.add(folder)
            text = json.dumps({"input_required": {"question": "Should I preserve the Java public API?"}})
            return SimpleNamespace(text=text, events=[], usage=[])
        if folder in asked:
            assert '"human_reply": "Convert the Java code to Rust"' in request.prompt
        return model(request, **kwargs)
    monkeypatch.setattr(engine, "run_opencode", clarify)
    monkeypatch.setattr(domain.solver, "require_openshell", lambda: None)
    config = resolve_config(read_blueprint(BLUEPRINT)).data
    config["harness"]["mode"] = mode
    block = context(tmp_path, config=config)
    admitted = domain.intake.prepare(block, {"task": "Convert to Rust"})
    solved = domain.solver.solve(context(tmp_path, step="solve_task", config=config), {"previous": admitted})
    result = block.store.read(solved["outcome"])["data"]
    assert result["status"] == "completed", failures
    questions = [event for event in conversation_events if event["type"] == "human_input_requested"]
    assert len(questions) == 1
    assert len(asked) == 4  # A single authoritative reply is reused across probes.
    assert any(event["type"] == "human_notice" for event in conversation_events)


@pytest.mark.parametrize("event", [
    {"type": "human_input_timeout", "payload": {}},
    {"type": "human_input_received", "payload": {"request_id": "another-run", "notes": "Invented"}},
])
def test_missing_or_foreign_human_reply_cannot_resume_task(domain, monkeypatch, tmp_path, event):
    conversation = importlib.import_module("domain.conversation")
    monkeypatch.setattr(conversation.human_interactions, "await_human_decision", lambda *args, **kwargs: event)
    with pytest.raises(RuntimeError, match="reply in Chat"):
        domain.intake.prepare(context(tmp_path), {})
