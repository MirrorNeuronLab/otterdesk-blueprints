"""Native case phases execute through actual compiled workers, without legacy fixtures."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from mn_sdk.blueprints import compile_blueprint, read_blueprint, resolve_config
from mn_sdk.blueprints.worker_descriptors import resolved_worker_descriptor
from mn_sdk.integrations.block_worker import run
from mn_sdk.step_runtime import StepContext
from mn_sdk_common.committed_artifacts import CommittedJsonStore

ROOT = Path(__file__).resolve().parents[2] / "litigation_analyst"


@pytest.fixture
def native_case(tmp_path, monkeypatch, request):
    monkeypatch.syspath_prepend(str(ROOT / "payloads"))
    from domain.graph_projection.projector import CaseGraphProjector
    from domain.graph_projection import build_records
    from mn_graph_analysis_skill import GraphClient

    calls = []

    def project(graph, documents, **options):
        records = build_records(documents, repository_id=options.get("repository_id"), file_identities=options.get("file_identities"))
        calls.append(records)
        graph.graph_path.write_bytes(hashlib.sha256(repr(records).encode()).digest())

    monkeypatch.setattr(CaseGraphProjector, "project", project)
    monkeypatch.setattr(GraphClient, "check", lambda self: "ok")
    package = read_blueprint(ROOT)
    configuration = resolve_config(package, {"model_preflight": {"enabled": False},
        "source_relationships": {"mode": "structural"}, "review": {"profile": "standard"},
        **getattr(request, 'param', {})})
    compiled = compile_blueprint(package, configuration).manifest
    descriptor = tmp_path / "manifest.json"
    descriptor.write_text(json.dumps(resolved_worker_descriptor(package, compiled, configuration)))
    env = {"MN_RUN_DIR": str(tmp_path / "run"), "MN_BLUEPRINT_MANIFEST_PATH": str(descriptor),
        "MN_JOB_ID": "native-case-job", "MN_RUN_ID": "native-case-run", "MN_SDK_COMPONENTS_JSON": '["blueprint-blocks"]'}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    folder = tmp_path / "inputs"
    folder.mkdir()
    original = "Approval notice. Routine duties explain the correspondence."
    (folder / "notice.txt").write_text(original)
    marker = tmp_path / "source-was-executed"
    (folder / "untrusted.py").write_text(f"from pathlib import Path\nPath({str(marker)!r}).write_text('executed')\n")
    store = CommittedJsonStore(tmp_path / "run")

    def execute(step_id, inputs, *, config=None, template=None, identity=None, model=None):
        if template:
            implementation = compiled['workflow']['child_workflows']['investigate_case_evidence']['templates'][template]['implementation']
            assert implementation['handler'] == 'mn_sdk.integrations.block_worker'
            parameters = implementation['with']
            agent_id = template
        else:
            node = next(node for node in compiled["agents"]["nodes"] if node.get("config", {}).get("environment", {}).get("MN_WORKFLOW_STEP_HANDLER") == "mn_sdk.integrations.block_worker"
                and json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"]).get("block_step_id") == step_id)
            parameters = json.loads(node["config"]["environment"]["MN_WORKFLOW_STEP_WITH_JSON"])
            agent_id = node['node_id']
        context = StepContext(step_id=step_id, agent_id=agent_id, job_id="native-case-job", run_id="native-case-run",
            idempotency_key=f"native-case-run/{identity or step_id}", environment=env, config=config or configuration.data,
            message={"body": {"step_input": inputs}})
        return run(context, **parameters, resources={'llm': model} if model else {})

    def investigate(model):
        captured = execute('prepare_case_sources', {'input_folder': str(folder)})
        indexed = execute('build_case_indexes', {'previous': captured.outputs})
        initialized = execute('investigate_case_evidence', {'previous': indexed.outputs})
        for revision in range(3):
            inputs = {'seed': initialized.outputs['result'], '_child': {'round': revision, 'revision': revision}}
            identity = f'plan/{revision}'
            plan = execute('plan_litigation_round', inputs, template='plan_litigation_round', identity=identity, model=model)
            assert execute('plan_litigation_round', inputs, template='plan_litigation_round', identity=identity, model=model) == plan
            if plan.outputs['child_plan']['decision'] == 'stop':
                return plan.outputs['child_plan']['output']
            completed = set()
            for task in plan.outputs['child_plan']['steps']:
                assert set(task['needs']) <= completed
                work = {**task['input'], '_child': inputs['_child']}
                options = {'template': task['template'], 'identity': f"{revision}/{task['id']}", 'model': model}
                result = execute(task['template'], work, **options)
                assert execute(task['template'], work, **options) == result
                assert len(json.dumps(result.outputs)) < 2048
                completed.add(task['id'])
        pytest.fail('compiled investigation did not reach its terminal summary')

    return SimpleNamespace(execute=execute, store=store, folder=folder, original=original,
        calls=calls, marker=marker, config=configuration.data, investigate=investigate, environment=env)


def test_compiled_native_capture_and_index_preserve_frozen_sources(native_case):
    case = native_case
    inputs = {"input_folder": str(case.folder)}
    captured = case.execute("prepare_case_sources", inputs)
    case.folder.joinpath("notice.txt").write_text("changed after capture")
    assert case.execute("prepare_case_sources", inputs) == captured
    indexed = case.execute("build_case_indexes", {"previous": {"result": captured.outputs["result"]}})
    assert case.execute("build_case_indexes", {"previous": {"result": captured.outputs["result"]}}) == indexed
    result = case.store.read(indexed.outputs["result"])
    assert result["evidence"]["path"] == "case/indexed.json"
    assert case.original in case.store.path("case/sources.json").read_text()
    assert "changed after capture" not in case.store.path("case/sources.json").read_text()
    assert len(case.calls) == 1 and not case.marker.exists()
    assert len(json.dumps(indexed.outputs).encode()) < 2048


@pytest.mark.parametrize("fault", ["sources", "inventory", "original", "configuration", "wrong_phase"])
def test_native_index_rejects_changed_case_authority_before_graph_work(native_case, fault):
    case = native_case
    captured = case.execute("prepare_case_sources", {"input_folder": str(case.folder)})
    previous = captured.outputs["result"]
    config = None
    if fault == "sources":
        case.store.path("case/sources.json").write_text("[]")
    elif fault == "inventory":
        case.store.path("case/source_inventory.json").write_text("{}")
    elif fault == "original":
        next(case.store.path("case/originals").iterdir()).write_bytes(b"changed bytes")
    elif fault == "configuration":
        config = {**case.config, "investigation": {**case.config["investigation"], "access_scope": "other"}}
    else:
        wrong = case.store.commit("foreign.json", {})
        previous = case.store.commit("wrong-result.json", {"evidence": wrong.to_dict()}).to_dict()
    with pytest.raises((ValueError, RuntimeError)):
        case.execute("build_case_indexes", {"previous": {"result": previous}}, config=config)
    assert case.calls == []


@pytest.mark.parametrize('ui_failure', [False, True])
def test_compiled_case_rounds_publish_and_replay_verified_draft(native_case, monkeypatch, ui_failure):
    from test_dynamic_rounds import RoundModel
    from domain import workspace_web
    case = native_case
    if ui_failure:
        def unavailable(*args, **kwargs):
            raise OSError('synthetic renderer failure')
        monkeypatch.setattr(workspace_web, 'render', unavailable)
    model = RoundModel()
    terminal = case.investigate(model)
    database = case.store.path('case/evidence.sqlite3')
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    result = case.execute('write_review_draft', {'previous': terminal})
    assert case.execute('write_review_draft', {'previous': terminal}) == result
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    published = case.store.read(result.outputs['result'])
    assert published['status'] == 'draft_for_human_review'
    assert case.original in case.store.path('evidence_appendix.md').read_text()
    assert 'Approval notice' in case.store.path('final_report.md').read_text()
    assert case.store.path('case/workspace.json').exists()
    assert bool(published['web_ui']) is not ui_failure
    from mn_sdk.run_outputs import output_metadata
    downloads = output_metadata(case.store.run_dir)
    assert {item['name'] for item in downloads} == {
        'final_report.md', 'evidence_appendix.md', 'graph_appendix.md',
        'transaction_appendix.md', 'review_index.json',
    }
    for item in downloads:
        data = Path(item['path']).read_bytes()
        assert item['sha256'] == hashlib.sha256(data).hexdigest()
        assert item['size_bytes'] == len(data)
    assert not any(item['relative_path'].startswith('case/') for item in downloads)
    assert not case.marker.exists() and len(case.calls) == 1
    assert len(json.dumps(result.outputs)) < 2048
    count = len(model.calls)
    case.store.path('final_report.md').write_text('tampered after success')
    with pytest.raises(ValueError, match='hash mismatch'):
        case.execute('write_review_draft', {'previous': terminal})
    assert len(model.calls) == count


def test_native_publication_recovers_failed_export_without_repeating_investigation(native_case, tmp_path, monkeypatch):
    from test_dynamic_rounds import RoundModel
    from domain import reporting
    case = native_case
    model = RoundModel()
    terminal = case.investigate(model)
    count = len(model.calls)
    original = reporting.copy_path_to_host
    attempts = []
    def export(source, target):
        attempts.append(target)
        if len(attempts) == 1:
            raise OSError('synthetic interrupted export')
        return original(source, target)
    monkeypatch.setattr(reporting, 'copy_path_to_host', export)
    destination = tmp_path / 'delivered'
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR', str(destination))
    case.environment['MN_JOB_OUTPUT_DIR'] = str(destination)
    with pytest.raises(OSError, match='interrupted export'):
        case.execute('write_review_draft', {'previous': terminal})
    published = case.execute('write_review_draft', {'previous': terminal})
    assert case.execute('write_review_draft', {'previous': terminal}) == published
    assert len(attempts) == 2 and len(model.calls) == count
    assert (destination / 'final_report.md').exists()
    assert (destination / 'runs/run/case/evidence.sqlite3').exists()
    assert (destination / 'final_report.md').read_text().startswith('Audit paths below are relative to `runs/run/`.')
    assert json.loads((destination / 'review_index.json').read_text())['audit_root'] == 'runs/run'


@pytest.mark.parametrize('native_case', [{'text_memory': {'enabled': False}}], indirect=True)
def test_compiled_case_uses_real_sdk_fake_models_through_planning_and_publication(native_case, monkeypatch):
    from mn_sdk.llm import LLMClient
    from mn_sdk.model_access import runtime
    from mn_sdk.run_outputs import output_metadata

    def no_live_model(*_args, **_kwargs):
        pytest.fail('Fake execution must not prepare or contact a live model')
    monkeypatch.setenv('MN_BLUEPRINT_FAKE_LLM', '1')
    monkeypatch.setattr(runtime.urllib.request, 'urlopen', no_live_model)
    monkeypatch.setattr(runtime, '_default_client_factory', no_live_model)
    case = native_case
    # The compiled descriptor selects the documented memory-free profile because
    # this fixture's source transport cannot hydrate authored records across corpora.
    terminal = case.investigate(LLMClient(strict=True, provider='fake'))
    proposal = json.loads(case.store.path('case/rounds/proposal-00.json').read_text())['proposal']
    assert proposal['decision'] == 'execute' and proposal['hypotheses']
    assert all(item['support_query'] != item['counter_query'] for item in proposal['hypotheses'])
    result = case.execute('write_review_draft', {'previous': terminal})
    assert case.execute('write_review_draft', {'previous': terminal}) == result
    assert {item['name'] for item in output_metadata(case.store.run_dir)} == {
        'final_report.md', 'evidence_appendix.md', 'graph_appendix.md',
        'transaction_appendix.md', 'review_index.json',
    }


def test_domain_file_postconditions_preserve_large_case_artifacts(native_case):
    from mn_blueprint_blocks.context import BlockContext
    from domain.state import file_record, verify_files
    case = native_case
    context = BlockContext(case.store, 'large-file', 'test@1', config=case.config)
    path = case.store.path('case/large-workspace.json')
    path.parent.mkdir(parents=True)
    with path.open('wb') as stream:
        stream.truncate(64 * 1024 * 1024 + 1)
    record = file_record(context, 'case/large-workspace.json')
    assert record['size_bytes'] > 64 * 1024 * 1024
    verify_files(context, [record])
    with path.open('r+b') as stream:
        stream.write(b'x')
    with pytest.raises(ValueError, match='hash mismatch'):
        verify_files(context, [record])
