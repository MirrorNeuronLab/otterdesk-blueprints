"""Compiled native phases with real syntax/report skills and a mocked RGX transport."""

import hashlib
import json
from pathlib import Path

import pytest

from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.published_outputs import published_output_items
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import (
    CommittedArtifactIntegrityError,
    CommittedJsonStore,
)


@pytest.fixture
def native(tmp_path, monkeypatch, architecture_paths):
    from mn_graph_analysis_skill import GraphClient

    root = Path(__file__).resolve().parents[2] / "software_architecture_advisor"
    config = json.loads((root / "config/default.json").read_text())
    config.update(offline=True)
    config["text_memory"]["enabled"] = False
    config["source_search"]["mode"] = "lexical"
    config["inputs"]["payload"]["repository_url"] = ""
    package = read_blueprint(root)
    configuration = resolve_config(package, config)
    config = configuration.data
    compiled = compile_blueprint(package, configuration).manifest
    revision = compiled["metadata"]["mn_blocks_lock"]["revision"]
    descriptor = tmp_path / "runtime/manifest.json"
    descriptor.parent.mkdir()
    descriptor.write_text(
        json.dumps(resolved_worker_descriptor(package, compiled, configuration))
    )
    source = tmp_path / "repository"
    source.mkdir()
    marker = tmp_path / "source-was-executed"
    (source / "app.py").write_text(
        f"from pathlib import Path\nPath({str(marker)!r}).touch()\ndef run():\n    return helper()\ndef helper():\n    return 1\n"
    )
    store = CommittedJsonStore(tmp_path / "submission/outputs/runs/native-run")
    env = {
        "MN_RUN_DIR": str(store.run_dir),
        "MN_WORKFLOW_RUN_ID": "native-run",
        "MN_JOB_ID": "native-job",
        "MN_JOB_DATA_DIR": str(tmp_path / "job-data"),
        "MN_JOB_OUTPUT_DIR": str(tmp_path / "delivery"),
        "MN_JOB_SHARED_STORAGE_ROOT": str(tmp_path / "submission"),
        "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
        "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]',
    }
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    imports = []

    def graph_import(client, nodes, edges):
        # The shared skills construct real source-linked JSON. Only the native
        # RGX process is substituted; these tests do not qualify that binary.
        content = Path(nodes).read_bytes() + Path(edges).read_bytes()
        client.database_path.write_bytes(hashlib.sha256(content).digest())
        imports.append(str(client.database_path))

    monkeypatch.setattr(GraphClient, "import_json", graph_import)
    monkeypatch.setattr(GraphClient, "check", lambda *_: None)

    def invoke(step, inputs, *, phase="execute", identity=None):
        context = StepContext(
            step_id=step,
            run_id="native-run",
            job_id="native-job",
            job_data_dir=env["MN_JOB_DATA_DIR"],
            idempotency_key=identity or step,
            config=config,
            environment=env,
            message={"_mn_step": {"step_input": inputs}},
        )
        return run(context, block_step_id=step, revision=revision, phase=phase)

    invoke.config = config
    return store, source, marker, imports, invoke


def prepare(native):
    store, source, _, _, invoke = native
    capture = invoke(
        "capture_repository",
        {"input_folder": str(source), "goal": "Inspect captured functions"},
    )
    structure = invoke("analyze_dependency_structure", {"previous": capture.outputs})
    initialized = invoke("investigate_architecture", {"previous": structure.outputs})
    work = {
        "seed": initialized.outputs["result"],
        "_child": {"round": 0, "revision": 0},
    }
    terminal = invoke("investigate_architecture", work, phase="plan", identity="plan-0")
    assert terminal.outputs["child_plan"]["decision"] == "stop"
    summary = terminal.outputs["child_plan"]["output"]["result"]
    return capture, structure, {"previous": {"result": summary}}


@pytest.mark.parametrize("source_kind, error, message", [
    ("missing", ValueError, "Specify exactly one"),
    ("unavailable", FileNotFoundError, "missing"),
    ("file", ValueError, "must be a directory"),
    ("ambiguous", ValueError, "Specify exactly one"),
])
def test_capture_rejects_unanswered_or_invalid_sources_before_analysis(
    native, source_kind, error, message
):
    store, source, marker, imports, invoke = native
    inputs = {}
    if source_kind == "unavailable":
        inputs["input_folder"] = str(source / "missing")
    elif source_kind == "file":
        inputs["input_folder"] = str(source / "app.py")
    elif source_kind == "ambiguous":
        inputs = {
            "input_folder": str(source),
            "repository_url": "https://github.com/example/repository",
        }

    with pytest.raises(error, match=message):
        invoke("capture_repository", inputs)

    assert imports == []
    assert not marker.exists()
    assert not store.path("snapshot.json").exists()
    assert not store.path("capture-request.json").exists()


def test_compiled_native_capture_to_publication_preserves_evidence_and_replay(native):
    store, source, marker, imports, invoke = native
    capture, structure, publish_input = prepare(native)
    result = invoke("publish_architecture_review", publish_input)
    value = store.read(result.outputs["result"])
    assert value["status"] == "partial"
    assert not marker.exists()
    assert store.path("data/static-code.json").is_file()
    assert store.path("reports/report.md").is_file()
    assert store.path("web/index.html").is_file()
    assert len(store.read_path("data/coverage.json")["aspects"]) == 150
    public = published_output_items(store.run_dir)
    names = {item['path'] for item in public}
    assert {'reports/report.md', 'data/report.json', 'review_index.json', 'web/index.html', 'web_ui.json'} <= names
    assert all(name in {'review_index.json', 'web_ui.json'} or name.startswith(('data/', 'web/', 'reports/')) for name in names)
    handle = store.read_path('web_ui.json')
    assert handle['kind'] == 'output' and handle['adapter'] == 'static_html'
    assert handle['metadata']['sha256'] == hashlib.sha256(store.path('web/index.html').read_bytes()).hexdigest()
    assert handle['metadata']['optional'] is False
    assert (store.run_dir.parents[3] / 'delivery/web_ui.json').read_bytes() == store.path('web_ui.json').read_bytes()
    for item in public:
        encoded = store.path(item['path']).read_bytes()
        assert item['size_bytes'] == len(encoded)
        assert item['sha256'] == hashlib.sha256(encoded).hexdigest()
    before = list(imports)
    (source / "app.py").write_text("changed after capture")
    assert (
        invoke(
            "capture_repository",
            {"input_folder": str(source), "goal": "Inspect captured functions"},
        )
        == capture
    )
    assert (
        invoke("analyze_dependency_structure", {"previous": capture.outputs})
        == structure
    )
    assert invoke("publish_architecture_review", publish_input) == result
    assert published_output_items(store.run_dir) == public
    assert imports == before
    assert store.read_path("catalog/terminal.json")["usage"]["catalog_models"] == 0
    assert (store.run_dir.parents[3] / "delivery/reports/report.md").is_file()


@pytest.mark.parametrize("fault", ["snapshot", "sources", "config", "scope"])
def test_capture_authority_is_required_before_structural_work(native, fault):
    from domain.state import read_state
    from native_test_support import block_context

    store, source, _, imports, invoke = native
    captured = invoke("capture_repository", {"input_folder": str(source)})
    value = store.read(captured.outputs["result"])
    initial = len(imports)
    if fault in {"snapshot", "sources"}:
        packet = store.read(value["evidence"])
        path = (
            "snapshot.json"
            if fault == "snapshot"
            else next(
                name for name in packet["files"] if name.endswith("/sources.json")
            )
        )
        store.path(path).write_text("{}")
        with pytest.raises(ValueError, match="working evidence"):
            invoke("analyze_dependency_structure", {"previous": captured.outputs})
    else:
        block = block_context(
            {
                "run_dir": store.run_dir,
                "run_id": "native-run",
                "job_id": "native-job",
                "config": invoke.config if fault == "scope" else {},
            }
        )
        if fault == "scope":
            block.run_id = "another-run"
        with pytest.raises(ValueError, match="phase, run or configuration"):
            read_state(block, value["evidence"], "capture")
    assert len(imports) == initial


def test_required_dashboard_failure_keeps_data_and_replays_without_research(
    native, monkeypatch
):
    from domain import workspace_web

    store, _, _, imports, invoke = native
    _, _, work = prepare(native)
    before = list(imports)
    original = workspace_web.render
    monkeypatch.setattr(
        workspace_web,
        "render",
        lambda *a, **k: (_ for _ in ()).throw(
            RuntimeError("injected required UI failure")
        ),
    )
    with pytest.raises(RuntimeError, match="required UI failure"):
        invoke("publish_architecture_review", work)
    assert store.path("data/report.json").is_file()
    monkeypatch.setattr(workspace_web, "render", original)
    result = invoke("publish_architecture_review", work)
    assert store.read(result.outputs["result"])["status"] == "partial"
    assert imports == before


def test_publication_replay_rejects_changed_terminal_authority(native):
    store, _, _, _, invoke = native
    _, _, work = prepare(native)
    invoke("publish_architecture_review", work)
    store.path("catalog/terminal.json").write_text("{}")
    with pytest.raises(CommittedArtifactIntegrityError):
        invoke("publish_architecture_review", work)


def test_required_download_delivery_failure_replays_without_research(native, monkeypatch):
    from domain import catalog_publication

    store, _, _, imports, invoke = native
    _, _, work = prepare(native)
    before = list(imports)
    original = catalog_publication.deliver_files
    monkeypatch.setattr(catalog_publication, 'deliver_files',
        lambda *a, **k: (_ for _ in ()).throw(OSError('injected download delivery failure')))
    with pytest.raises(OSError, match='download delivery failure'):
        invoke('publish_architecture_review', work)
    assert store.path('reports/report.md').is_file()
    assert published_output_items(store.run_dir) == []
    monkeypatch.setattr(catalog_publication, 'deliver_files', original)
    result = invoke('publish_architecture_review', work)
    assert store.read(result.outputs['result'])['status'] == 'partial'
    assert any(item['path'] == 'reports/report.md' for item in published_output_items(store.run_dir))
    assert imports == before


def test_publication_rejects_a_source_reference_in_place_of_terminal_authority(native):
    store, source, _, _, invoke = native
    captured = invoke("capture_repository", {"input_folder": str(source)})
    source_reference = store.read(captured.outputs["result"])["snapshot"]
    # Match the real artifact-valued upstream port; a status string alone must
    # never make a source snapshot into an investigation completion record.
    wrong = store.commit(
        "fixture/wrong-summary.json", {"status": "partial", "catalog": source_reference}
    )
    with pytest.raises(ValueError, match="different authority"):
        invoke("publish_architecture_review", {"previous": {"result": wrong.to_dict()}})
    assert not store.path("data/report.json").exists()
