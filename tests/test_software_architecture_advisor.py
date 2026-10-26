import ast
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from mn_sdk.blueprints import read_blueprint, resolve_config, compile_blueprint, blueprint_definition, catalog_record
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / 'software_architecture_advisor'

@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT/'payloads'))
    monkeypatch.syspath_prepend(str(ROOT/'tests/software_architecture_advisor'))
    for repo in ['mn-skills','mn-agents']:
        for path in (companion_workspace(ROOT)/repo).glob('*/src'):
            monkeypatch.syspath_prepend(str(path))
    return {n: importlib.import_module('domain.'+n) for n in ['inputs','intake','model','improvement_prompts','config']}


def test_compiled_contract_and_docker_handlers(modules):
    package = read_blueprint(BLUEPRINT)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package, resolve_config(package)).manifest
    resources = {r['name']: r for r in compiled['metadata']['job_data']['resources']}
    assert resources['architecture_results']['path'] == 'architecture_results'
    assert resources['architecture_results']['access'] == 'read_write'
    fields = compiled['metadata']['run_retry']['configuration_fields']
    assert fields['catalog_review.walltime_seconds'] == {'type': 'integer', 'minimum': 1, 'maximum': 604800}
    assert fields['llm.max_calls']['maximum'] == 10000
    assert 'inputs.payload.input_folder' not in fields
    from mn_sdk.submission_preparation import lower_manifest_topology_for_runtime_submission
    lower_manifest_topology_for_runtime_submission(compiled)
    assert 'investigate_architecture' in compiled['flow']['child_workflows']
    steps = {item['id']: item for item in source['workflow']['steps']}
    assert steps['analyze_dependency_structure']['needs'] == ['capture_repository']
    assert steps['investigate_architecture']['needs'] == ['analyze_dependency_structure']
    assert steps['investigate_architecture']['control']['timeout_seconds'] == 604800
    runtime_steps = {item['id']: item for item in compiled['flow']['steps']}
    assert runtime_steps['investigate_architecture']['control']['timeout_seconds'] == 604800
    worker = next(node for node in compiled['agents']['nodes']
                  if node['node_id'] == 'investigate_architecture__block_investigate_architecture_specialist')
    assert worker['config']['timeout_seconds'] == 604800
    assert worker['config']['environment']['MN_WORKFLOW_STEP_HANDLER'] == 'mn_sdk.integrations.block_worker'
    binding = json.loads(worker['config']['environment']['MN_WORKFLOW_STEP_WITH_JSON'])
    assert binding['revision'] == compiled['metadata']['mn_blocks_lock']['revision']
    assert steps['publish_architecture_review']['needs'] == ['investigate_architecture']
    assert len(compiled['agents']['nodes']) >= 9
    assert source['response_service'] == {'enabled': True}
    assert source['contracts']['inputs']['input_folder']['type'] == 'local_path'
    assert source['input_validation']['rules'][0]['command'] == [
        '/usr/bin/python3',
        'payloads/agents/validation/validate_source_input.py',
    ]
    for name, record in source['agents']['registry'].items():
        assert name not in {s['id'] for s in source['workflow']['steps']}
        assert callable(importlib.import_module(record['handler']).run)
    groups = json.loads((BLUEPRINT/'execution.json').read_text())['workers']['groups']
    assert groups[0]['uses'] == 'mn-agents.worker.python_docker@1'
    review = next(g for g in groups if 'review_architecture_packet' in g['steps'])
    assert review['with']['runner_module'] == 'MirrorNeuron.Runner.OpenShell'
    assert review['with']['artifact_handoff']['version'] == 'mn.artifact_handoff/v1'
    assert not review['with'].get('sync_shared_storage')
    child = compiled['flow']['child_workflows']['investigate_architecture']
    assert child['max_rounds'] == 20 and child['max_steps_per_round'] == 64


def test_default_output_uses_sdk_host_copy_contract(tmp_path, monkeypatch):
    from mn_sdk.submission import prepare_job_submission

    config=json.loads((BLUEPRINT/'config/default.json').read_text())
    execution=json.loads((BLUEPRINT/'execution.json').read_text())
    assert 'output_folder' not in config
    assert not config['inputs']['payload'].get('repository_url')
    assert config['inputs']['payload']['input_folder'] == ''
    assert execution['job_name']=='software_architecture_advisor'
    assert config['outputs']['folder_path']==f"~/Downloads/{execution['job_name']}"
    assert config['outputs']['write_run_store'] is True
    assert config['outputs']['job_files'] == ['data', 'web', 'reports', 'web_ui.json']

    monkeypatch.setenv('HOME',str(tmp_path))
    manifest={
        'apiVersion':'mn.workflow/v1', 'kind':'Workflow', 'id':'software_architecture_advisor',
        'job_name':execution['job_name'], 'contract':{}, 'runtime':{},
        'agents':{'nodes':[{'node_id':'report', 'config':{'environment':{
            'MN_BLUEPRINT_CONFIG_JSON':json.dumps(config),
        }}}]},
    }
    prepared=prepare_job_submission(manifest, {}, shared_storage_root=tmp_path/'shared',
                                    runtime_shared_storage_root='/remote/shared')
    copies=json.loads(prepared.manifest_json)['metadata']['mn_storage']['output_copy']
    assert any(item['target_path']==str(tmp_path/'Downloads/software_architecture_advisor')
               for item in copies)
    assert all({'data', 'web', 'reports', 'web_ui.json'} <= set(item['job_files']) for item in copies)


def test_delivered_dashboard_keeps_its_handle_beside_the_job_web_folder(tmp_path):
    from mn_sdk.blueprint_support.shared_outputs import materialize_shared_storage_outputs
    from mn_sdk_web_ui import static_run_report_handle

    config = json.loads((BLUEPRINT / 'config/default.json').read_text())
    host = tmp_path / 'shared'
    submission = host / 'submissions/job'
    source = submission / 'outputs/runs/review'
    (source / 'web').mkdir(parents=True)
    page = b'<html><body>Architecture report</body></html>'
    (source / 'web/index.html').write_bytes(page)
    handle = static_run_report_handle(source, 'web/index.html', title='Architecture review', optional=False)
    (source / 'web_ui.json').write_text(json.dumps(handle))
    target = tmp_path / 'Downloads/architecture'
    storage = {'host_root': str(host), 'runtime_root': '/runtime/shared',
        'host_submission_path': str(submission), 'run_id': 'review', 'output_copy': [{
            'source_path': '/runtime/shared/submissions/job/outputs/runs/review',
            'target_path': str(target), 'layout': 'batch', 'job_files': config['outputs']['job_files']}]}
    result = materialize_shared_storage_outputs(storage, publish_results=False)
    assert not result['errors']
    assert (target / 'web/index.html').read_bytes() == page
    assert json.loads((target / 'web_ui.json').read_text()) == handle


def test_structural_baseline_has_source_linked_edges_cycles_and_bounded_dsm(modules, tmp_path):
    import csv
    from domain.structural_analysis import analyze_dependencies, _write_dsm

    snapshot = {'id': 'frozen', 'modules': {name: {'path': f'{name}.py'} for name in ('a', 'b', 'c')},
                'coverage': {'source_files': 3, 'skipped': {}}}
    nodes = [{'id': index, 'properties': {'key': f'module:{name}'}}
             for index, name in enumerate(('a', 'b', 'c'), 1)]
    pairs = [(1, 2), (2, 1), (3, 2)]
    edges = [{'src': source, 'dst': target, 'rel_type': 'DEPENDS_ON',
              'properties': {'evidence_ids': [f'E{index}']}}
             for index, (source, target) in enumerate(pairs, 1)]
    evidence = {f'E{index}': {'path': f'{"abc"[source-1]}.py', 'sha256': 'frozen-hash',
                              'line_start': index, 'line_end': index}
                for index, (source, _) in enumerate(pairs, 1)}

    result, adjacency = analyze_dependencies(snapshot, nodes, edges, evidence, max_dsm_modules=3)
    assert result['strongly_connected_cycles'] == [['a', 'b']]
    assert result['bridge_modules'] == ['b']
    assert result['fan_in'] == {'a': 1, 'b': 2, 'c': 0}
    assert result['dependencies'][0]['source_locations'][0]['path'] == 'a.py'
    assert result['dsm']['status'] == 'ready'
    path = tmp_path / 'dsm.csv'
    _write_dsm(path, result['modules'], adjacency)
    with path.open(newline='') as file:
        assert list(csv.reader(file)) == [
            ['module', 'a', 'b', 'c'], ['a', '0', '1', '0'],
            ['b', '1', '0', '0'], ['c', '0', '1', '0']]

    limited, _ = analyze_dependencies(snapshot, nodes, edges, evidence, max_dsm_modules=2)
    assert limited['dsm']['status'] == 'omitted_size_limit'
    assert len(limited['dependencies']) == 3
    with pytest.raises(ValueError, match='evidence'):
        analyze_dependencies(snapshot, nodes, edges, {}, max_dsm_modules=3)


def test_desktop_setup_only_asks_for_an_unfilled_source_folder(modules):
    ui=catalog_record(read_blueprint(BLUEPRINT), 'software_architecture_advisor')
    guide=ui['setup_guide']
    assert guide['sample']['available'] is False
    assert len(guide['fields']) == 1
    field = guide['fields'][0]
    assert field['path'] == 'inputs.payload.input_folder'
    assert field['required'] is True and field['default'] == ''
    assert field['type'] == 'local_path' and field['path_kind'] == 'directory'
    assert guide['real']['values'] == {'inputs.payload.input_folder': ''}
    assert ui['init_config_review']['fields'] == []
    assert ui['web_ui']['enabled'] is True
    assert ui['web_ui']['adapter'] == 'static_html' and ui['web_ui']['kind'] == 'output'
    assert modules['intake'].source_input({
        'repository_url': '',
        'input_folder': str(BLUEPRINT/'examples/sample_repository'),
    })==str(BLUEPRINT/'examples/sample_repository')


def test_presentation_prompt_retains_source_and_untrusted_boundaries(modules):
    # The native catalog publisher's report/work-package/JSON file equivalence
    # is exercised in test_workspace_output. This checks its current prompt data
    # contract instead of the removed hypothesis-report helper functions.
    workspace = {
        'id': 'retained', 'snapshot_id': 'source', 'repository_id': 'payments',
        'revision': 'a'*40, 'status': 'partial', 'goal': 'Review payment retries',
        'files': [{'path': 'payments/service.py'}],
        'evidence': [{'id': 'E1', 'path': 'payments/service.py', 'sha256': 'b'*64,
            'start_line': 1, 'end_line': 1, 'excerpt': 'def pay(): pass\n'}],
        'findings': [{'id': 'H01', 'statement': 'Review the retry boundary',
            'evidence_ids': ['E1'], 'counterevidence_ids': []}],
        'recommendations': [], 'work_packages': [], 'claims': [], 'checks': [],
        'cycles': [], 'gaps': [],
    }
    workspace['improvement_prompts'] = modules['improvement_prompts'].build(workspace)
    prompt = workspace['improvement_prompts']['prompts'][0]
    assert prompt['record_id'] == 'H01' and prompt['mode'] == 'Investigate'
    assert prompt['evidence_ids'] == ['E1']
    assert prompt['target_files'] == ['payments/service.py']
    assert '--- BEGIN UNTRUSTED REPORT CONTEXT (JSON) ---' in prompt['prompt']
    assert 'b'*64 in prompt['prompt'] and 'def pay(): pass' in prompt['prompt']
    assert prompt['prompt'].rstrip() in modules['improvement_prompts'].markdown(workspace)


@pytest.mark.parametrize('payload',[{}, {'input_folder':'x','repository_url':'https://github.com/a/b'},
    {'repository_url':'http://github.com/a/b'}, {'repository_url':'https://token@github.com/a/b'},
    {'repository_url':'https://github.com:443/a/b'}, {'repository_url':'https://github.com/a/b/tree/main'},
    {'repository_url':'https://github.com/a/b?token=x'}, {'repository_url':'https://github.com/a/..'},
    {'repository_url':'file:///tmp/a'}, {'input_folder':'https://github.com/a/b'}, {'input_folder':''}])
def test_invalid_or_ambiguous_inputs_fail(modules,payload):
    with pytest.raises(ValueError): modules['intake'].source_input(payload)


def test_folder_with_spaces_and_canonical_url(modules,tmp_path):
    folder=tmp_path/'source folder';folder.mkdir()
    assert modules['intake'].source_input({'input_folder':str(folder)})==str(folder)
    assert modules['intake'].source_input({'repository_url':'https://github.com/a/b/'})=='https://github.com/a/b.git'


def test_shared_input_validation_requires_a_source_folder_first(tmp_path):
    from mn_sdk import run_input_validation

    package = read_blueprint(BLUEPRINT)
    manifest = blueprint_definition(package)
    config = resolve_config(package).data

    missing = run_input_validation(BLUEPRINT, manifest, config=config)

    assert missing['ok'] is False
    issue = missing['issues'][0]
    assert issue['code'] == 'config.required'
    assert '--set inputs.payload.input_folder=' in issue['help']

    source = tmp_path / 'source folder'
    source.mkdir()
    valid_config = json.loads(json.dumps(config))
    valid_config['inputs']['payload']['repository_url'] = None
    valid_config.setdefault('inputs', {}).setdefault('payload', {})['input_folder'] = str(source)

    assert run_input_validation(BLUEPRINT, manifest, config=valid_config)['ok'] is True


def test_clone_transport_restrictions_and_cleanup(modules,tmp_path,monkeypatch):
    import subprocess
    calls=[]
    def clone(command,**options):
        calls.append((command, options))
        raise subprocess.TimeoutExpired('git',1)
    monkeypatch.setattr(modules['inputs'].subprocess,'run',clone)
    cfg={'source':{'clone_timeout_seconds':1},'ingest':{'git_commits':20}}
    with pytest.raises(RuntimeError, match='GitHub download failed'):
        modules['inputs'].resolve_source('https://github.com/a/b',tmp_path,cfg)
    assert list((tmp_path/'repositories').iterdir())==[]
    command,options=calls[0]
    assert 'http.followRedirects=false' in command and '--no-recurse-submodules' in command
    assert '--depth' in command and options['env']['GIT_TERMINAL_PROMPT']=='0'
    assert options['env']['GIT_CONFIG_GLOBAL']=='/dev/null'


def test_sdk_model_schema_budget_and_failure(modules,monkeypatch):
    cfg=modules['config'].validate_config(json.loads((BLUEPRINT/'config/default.json').read_text()))
    client=SimpleNamespace(model='test',provider='test',backend='auto',api_base=None,api_key='',required_capabilities=())
    model=modules['model'].JsonModel(cfg,client)
    calls=[]
    def transport(*args,**kwargs):
        calls.append((args,kwargs));return {'choices':[{'message':{'content':'{"result":"ok"}'},'finish_reason':'stop'}]}
    monkeypatch.setattr(modules['model'],'runtime_model_json_request',transport)
    assert model.complete('assess',{'text':'a'})=={'result':'ok'}
    assert calls[0][0][3]['response_format']['type']=='json_schema'
    assert calls[0][1]['num_retries']==0
    with pytest.raises(ValueError,match='Context budget'): model.complete('assess',{'text':'长'*5000})
    assert len(calls)==1
    monkeypatch.setattr(modules['model'],'runtime_model_json_request',lambda *a,**k: (_ for _ in ()).throw(OSError('offline')))
    with pytest.raises(RuntimeError,match='no synthetic'): model.complete('assess',{'text':'a'})
    assert model.calls[-1]['status']=='error'


def test_architecture_ownership():
    payload=BLUEPRINT/'payloads'
    assert not (payload/'agents/domain.py').exists()
    assert not list(payload.glob('*_domain'))
    for directory in ['runtime','steps']:
        for path in (payload/directory).glob('*.py'):
            tree=ast.parse(path.read_text())
            assert len(path.read_text().splitlines())<500
            assert not any(isinstance(n,ast.ImportFrom) and (n.module or '').split('.')[0] in {'domain','agents'} for n in ast.walk(tree))
    for path in (payload/'agents').glob('*.py'):
        assert all(s not in path.read_text() for s in ['redis','from_node','to_node','complete_step'])
    for name in ['graph','capture','lazy']:
        text=(payload/f'domain/{name}.py').read_text()
        assert 'mn_graph_analysis_skill' in text
        assert 'rgx_client' not in text
    assert not (payload/'domain/server.py').exists()
    assert all('rfm_platform' not in path.read_text() for path in payload.rglob('*.py'))


def test_neural_retrieval_uses_embedding_model_and_capability(modules, monkeypatch):
    from domain import ingest
    cfg = resolve_config(read_blueprint(BLUEPRINT)).data
    calls = []

    class RuntimeEmbedder:
        def encode(self, texts, input_type='document'):
            calls.append((texts, input_type))
            return [[3.0, 4.0]]

    configs = []
    def build(config):
        configs.append(config)
        return RuntimeEmbedder()
    monkeypatch.setattr(ingest, 'build_runtime_embedder', build)
    embedder = ingest.make_embedder(cfg)
    assert embedder.embed_document('source text') == pytest.approx((3.0, 4.0))
    assert embedder.embed_query('question') == pytest.approx((3.0, 4.0))
    assert calls == [(['source text'], 'document'), (['question'], 'query')]
    assert configs[0].embedding_provider == 'litellm_proxy'
    assert configs[0].embedding_model == 'docker.io/ai/embeddinggemma:latest'

    class FailingEmbedder:
        def encode(self, texts, input_type='document'):
            raise RuntimeError('Embedding capability unavailable')

    monkeypatch.setattr(ingest, 'build_runtime_embedder', lambda config: FailingEmbedder())
    with pytest.raises(RuntimeError, match='capability unavailable'):
        ingest.make_embedder(cfg).embed_document('source text')


def graph_config():
    import os
    binary=Path(os.environ.get('ADVISOR_RGX_BINARY','/not-installed/rgx'))
    if not binary.is_file(): pytest.skip('Published Linux RGX binary required')
    cfg=resolve_config(read_blueprint(BLUEPRINT)).data
    cfg['graph']['binary']=str(binary)
    cfg['offline']=True
    cfg['investigation']['max_hypotheses']=1
    return cfg


def test_three_workers_durable_replay_and_frozen_evidence(modules,tmp_path,monkeypatch):
    from native_test_support import invoke, block_context
    import shutil
    cfg=graph_config()
    cfg['text_memory']['enabled'] = False
    cfg['inputs']['payload']['repository_url'] = ''
    folder=tmp_path/'source folder'
    shutil.copytree(BLUEPRINT/'examples/sample_repository',folder)
    marker=tmp_path/'executed'
    (folder/'src/payments/injected.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    run=tmp_path/'run'
    monkeypatch.setenv('MN_RUN_DIR',str(run))
    monkeypatch.setenv('MN_BLUEPRINT_BUNDLE_DIR',str(BLUEPRINT))
    output=tmp_path/'output'
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR',str(output))
    context={'run_dir':run, 'run_id':'test-run', 'job_id':'test-job',
        'job_data_dir':tmp_path/'job', 'config':cfg, 'output_folder':output}
    steps=['capture_repository','analyze_dependency_structure','investigate_architecture','publish_architecture_review']
    inputs={'input_folder':str(folder),'goal':'Inspect payments.payment_service retry boundaries'}
    for index,step in enumerate(steps):
        first=invoke(context, step, inputs)
        assert all((run/ref['path']).exists() for ref in first.artifacts)
        assert len(json.dumps(first.outputs))<2000
        if index==0:
            (folder/'src/payments/payment_service.py').write_text('raise RuntimeError("changed after capture")\n')
        second=invoke(context, step, inputs)
        assert first.outputs==second.outputs
        if step == 'investigate_architecture':
            work = {'seed': first.outputs['result'], '_child': {'round': 0, 'revision': 0}}
            terminal = invoke(context, step, work, phase='plan', identity='plan-0')
            assert invoke(context, step, work, phase='plan', identity='plan-0') == terminal
            plan = terminal.outputs['child_plan']
            assert plan['decision'] == 'stop'  # Static-only mode admits no model tasks.
            inputs = {'previous': {'result': plan['output']['result']}}
        else:
            inputs = {'previous': first.outputs}
    assert not marker.exists()
    report=json.loads((run/'data/report.json').read_text())
    assert report['status']=='partial'
    assert report['terminal']['usage']['catalog_models']==0
    assert 'changed after capture' not in (run/'reports/report.md').read_text()
    for filename in ('reports/report.md','data/coverage.json','data/claims.json','data/verification_tasks.json','reports/work_packages/README.md'):
        assert (run/filename).is_file()
    assert len(list((run/'reports/sections').glob('*.md')))==6
    events=[json.loads(line) for line in (run/'events.log').read_text().splitlines()]
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1))
    assert all(not e['event'].startswith('run.') for e in events)
    snapshot=json.loads((run/'snapshot.json').read_text())
    sources=run/'evidence/snapshots'/snapshot['id']/'sources.json'
    value=json.loads(sources.read_text());next(iter(value.values()))['text']='tampered';sources.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='hash mismatch'):
        __import__('domain.catalog_reporting',fromlist=['assemble']).assemble(block_context(context))


def test_https_input_retains_real_checkout_revision(modules,tmp_path,monkeypatch):
    import subprocess,shutil
    from native_test_support import block_context
    cfg=graph_config()
    repo=tmp_path/'repo';shutil.copytree(BLUEPRINT/'examples/sample_repository',repo)
    def git(*args): return subprocess.run(['git','-C',str(repo),*args],check=True,capture_output=True,text=True)
    git('init');git('add','.');git('-c','user.name=Fixture','-c','user.email=fixture@example.test','commit','-m','fixture')
    head=git('rev-parse','HEAD').stdout.strip()
    actual=subprocess.run
    def clone(command,**options):
        if 'clone' in command:
            return actual(['git','clone','--no-local','--',str(repo),command[-1]],**options)
        return actual(command,**options)
    monkeypatch.setattr(modules['inputs'].subprocess,'run',clone)
    context={'run_dir':tmp_path/'run','payload':{'repository_url':'https://github.com/example/repo'},'config':cfg}
    block = block_context(context)
    result=modules['intake'].capture_input(block, context['payload'])
    snapshot=json.loads((context['run_dir']/'snapshot.json').read_text())
    assert snapshot['input']['revision']==head
    assert snapshot['input']['location']=='https://github.com/example/repo.git'
    assert Path(snapshot['input']['checkout'],'.git').is_dir()
    assert block.store.read(result['snapshot']) == snapshot
    assert all(block.store.path(ref['path']).is_file()
        for ref in block.store.read(result['evidence'])['files'].values())


def test_local_repository_input_uses_sdk_staging(tmp_path):
    from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads
    config = json.loads((BLUEPRINT / 'config/default.json').read_text())
    source = tmp_path / 'repository with spaces'
    source.mkdir()
    (source / 'module.py').write_text('def example(): pass\n')
    config['inputs']['payload']['input_folder'] = str(source)
    config['inputs']['payload']['repository_url'] = None
    payloads = {}
    result = stage_local_input_payloads(config, payloads, bundle_dir=BLUEPRINT)
    assert result['folders'][0]['file_count'] == 1
    assert config['inputs']['payload']['input_folder'] == 'mn_local_inputs/repository'
    assert payloads['mn_local_inputs/repository/module.py'] == b'def example(): pass\n'
