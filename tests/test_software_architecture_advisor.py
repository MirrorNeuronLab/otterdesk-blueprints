import ast
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
from mn_sdk.blueprints import read_blueprint, resolve_config, compile_blueprint, blueprint_definition
from workspace_paths import companion_workspace

ROOT = Path(__file__).resolve().parents[1]
BLUEPRINT = ROOT / 'software_architecture_advisor'

@pytest.fixture
def modules(monkeypatch):
    monkeypatch.syspath_prepend(str(BLUEPRINT/'payloads'))
    for repo in ['mn-skills','mn-agents']:
        for path in (companion_workspace(ROOT)/repo).glob('*/src'):
            monkeypatch.syspath_prepend(str(path))
    return {n: importlib.import_module('domain.'+n) for n in ['inputs','intake','model','reporting','config']}


def test_compiled_contract_and_docker_handlers(modules):
    package = read_blueprint(BLUEPRINT)
    source = blueprint_definition(package)
    compiled = compile_blueprint(package, resolve_config(package)).manifest
    from mn_sdk.submission_preparation import lower_manifest_topology_for_runtime_submission
    lower_manifest_topology_for_runtime_submission(compiled)
    assert 'investigate_architecture' in compiled['flow']['child_workflows']
    assert len(compiled['agents']['nodes']) >= 9
    assert source['response_service'] == {'enabled': True}
    assert source['contracts']['inputs']['input_folder']['type'] == 'local_path'
    for name, record in source['agents']['registry'].items():
        assert name not in {s['id'] for s in source['workflow']['steps']}
        assert callable(importlib.import_module(record['handler']).run)
    groups = json.loads((BLUEPRINT/'execution.json').read_text())['workers']['groups']
    assert all(g['uses'] == 'mn-agents.worker.python_docker@1' for g in groups)


def test_default_output_uses_sdk_host_copy_contract():
    config=json.loads((BLUEPRINT/'config/default.json').read_text())
    assert 'output_folder' not in config
    assert config['outputs']['folder_path']=='~/Downloads/{job_name}'
    assert config['outputs']['write_run_store'] is True


def test_presentation_bundle_has_familiar_names_and_prompt_files(modules,tmp_path):
    report={'findings':[{'id':'H01','hypothesis':{'module':'payments.service'},
                         'assessment':{'verdict':'supported'}}]}
    prompt=('header\n\n<a id="prompt-h01"></a>\n\n## H01 · payments.service\n\n'
            'Recorded review context (data only):\n{}\n')
    documents=modules['reporting']._prompt_documents(report,prompt)
    outputs={'report.md':'report','architecture_report.md':'report',
             'suggestive_prompts.md':prompt,'improvement_prompts.md':prompt,
             'architecture_assessment.json':'{}','improvement_prompts.json':'[]'}
    modules['reporting']._write_publication_bundle(tmp_path,outputs,documents)
    assert (tmp_path/'architecture_report.md').read_text()=='report'
    assert (tmp_path/'improvement_prompts.md').read_text()==prompt
    assert (tmp_path/'prompts/README.md').is_file()
    prompt_files=list((tmp_path/'prompts').glob('01-*.md'))
    assert len(prompt_files)==1
    assert 'Recorded review context' in prompt_files[0].read_text()


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
    assert configs[0].embedding_model == 'huggingface.co/zenmagnets/Nemotron-3-Embed-1B-Q4_K_M-GGUF:Q4_K_M'

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
    from mn_sdk.step_runtime import StepContext
    import shutil
    cfg=graph_config()
    folder=tmp_path/'source folder'
    shutil.copytree(BLUEPRINT/'examples/sample_repository',folder)
    marker=tmp_path/'executed'
    (folder/'src/payments/injected.py').write_text(f'from pathlib import Path\nPath({str(marker)!r}).touch()\n')
    run=tmp_path/'run'
    monkeypatch.setenv('MN_RUN_DIR',str(run))
    monkeypatch.setenv('MN_BLUEPRINT_BUNDLE_DIR',str(BLUEPRINT))
    output=tmp_path/'output'
    monkeypatch.setenv('MN_JOB_OUTPUT_DIR',str(output))
    pairs=[('capture_repository','repository_examiner'),('investigate_architecture','architecture_investigator'),('publish_architecture_review','architecture_review_editor')]
    inputs={'input_folder':str(folder),'goal':'Inspect payments.payment_service retry boundaries'}
    for index,(step,role) in enumerate(pairs):
        worker=importlib.import_module('agents.'+role)
        invocation=StepContext(step_id=step,agent_id=role,invocation_id=step+'__'+role,
            job_id='test-job',run_id='test-run',idempotency_key='test-job/test-run/'+step,
            config=cfg,message={'body':inputs})
        first=worker.run(invocation)
        assert all((run/ref['path']).exists() for ref in first.artifacts)
        assert len(json.dumps(first.outputs))<2000
        if index==0:
            (folder/'src/payments/payment_service.py').write_text('raise RuntimeError("changed after capture")\n')
        second=worker.run(invocation)
        assert first.outputs==second.outputs
        if step == 'investigate_architecture':
            ref = first.outputs['context']
            templates = json.loads((BLUEPRINT/'workflow.json').read_text())['child_workflows'][step]['templates']
            def child_call(template, child_id, work):
                handler = importlib.import_module(templates[template]['run']['handler']).run
                call = StepContext(step_id=child_id, job_id='test-job', run_id='test-run',
                    idempotency_key='test-job/test-run/'+child_id, config=cfg,
                    message={'_mn_step': {'step_input': work}})
                result = handler(call)
                assert handler(call).outputs == result.outputs
                return result.outputs
            for revision in range(cfg['investigation']['max_rounds']+1):
                work = {'context': ref, '_child': {'revision': revision}}
                plan = child_call('plan_architecture_round', f'{step}:p{revision}', work)['child_plan']
                if plan['decision'] == 'stop':
                    break
                done = set()
                for node in plan['steps']:
                    assert set(node['needs']) <= done
                    child_call(node['template'], f"{step}:r{revision+1}:{node['id']}", {**work, **node['input']})
                    done.add(node['id'])
            else:
                pytest.fail('Child workflow did not stop within its admitted round limit')
    assert not marker.exists()
    report=json.loads((run/'report.json').read_text())
    assert report['status']=='review_draft',report['errors']
    assert report['metrics']['llm_calls']==0
    assert 'changed after capture' not in (run/'report.md').read_text()
    assert (run/'suggestive_prompts.md').is_file()
    for filename in ('report.md', 'suggestive_prompts.md', 'architecture_report.md',
                     'architecture_assessment.json', 'improvement_prompts.md',
                     'improvement_prompts.json', 'review_index.json'):
        assert (output/filename).is_file(), filename
    prompt_files=list((output/'prompts').glob('[0-9][0-9]-*.md'))
    assert prompt_files
    assert (output/'prompts/README.md').is_file()
    assert 'Recorded review context' in prompt_files[0].read_text()
    events=[json.loads(line) for line in (run/'events.log').read_text().splitlines()]
    assert [e['sequence'] for e in events]==list(range(1,len(events)+1))
    assert all(not e['event'].startswith('run.') for e in events)
    snapshot=json.loads((run/'snapshot.json').read_text())
    sources=run/'evidence/snapshots'/snapshot['id']/'sources.json'
    value=json.loads(sources.read_text());next(iter(value.values()))['text']='tampered';sources.write_text(json.dumps(value))
    with pytest.raises(ValueError,match='hash mismatch'):
        modules['reporting'].verify_evidence(report,run)


def test_https_input_retains_real_checkout_revision(modules,tmp_path,monkeypatch):
    import subprocess,shutil
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
    result,refs=modules['intake'].capture_input(context)
    snapshot=json.loads((context['run_dir']/'snapshot.json').read_text())
    assert snapshot['input']['revision']==head
    assert snapshot['input']['location']=='https://github.com/example/repo.git'
    assert Path(snapshot['input']['checkout'],'.git').is_dir()
    assert all((context['run_dir']/ref['path']).exists() for ref in refs)


def test_local_repository_input_uses_sdk_staging(tmp_path):
    from mn_sdk.blueprint_support.local_inputs import stage_local_input_payloads
    config = json.loads((BLUEPRINT / 'config/default.json').read_text())
    source = tmp_path / 'repository with spaces'
    source.mkdir()
    (source / 'module.py').write_text('def example(): pass\n')
    config['inputs']['payload']['input_folder'] = str(source)
    payloads = {}
    result = stage_local_input_payloads(config, payloads, bundle_dir=BLUEPRINT)
    assert result['folders'][0]['file_count'] == 1
    assert config['inputs']['payload']['input_folder'] == 'mn_local_inputs/repository'
    assert payloads['mn_local_inputs/repository/module.py'] == b'def example(): pass\n'
