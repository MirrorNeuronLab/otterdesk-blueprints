from native_test_support import block_context
"""Real syntax facts, graph joins, focused model workflow and publication."""
import hashlib
import json
import os
from pathlib import Path

import pytest
from support import configuration


def captured(tmp_path, sources):
    root = tmp_path / 'submission/outputs/runs' / os.environ.get('MN_WORKFLOW_RUN_ID', 'run')
    folder = root / 'evidence/snapshots/frozen'
    folder.mkdir(parents=True)
    records = {p:{'text':t, 'sha256':hashlib.sha256(t.encode()).hexdigest()} for p,t in sources.items()}
    snapshot = {'id':'frozen', 'sources':{p:r['sha256'] for p,r in records.items()}, 'modules':{},
                'input':{'kind':'fixture'}, 'coverage':{'source_files':len(sources),'skipped':{}}, 'warnings':[]}
    (root/'snapshot.json').write_text(json.dumps(snapshot))
    (folder/'sources.json').write_text(json.dumps(records))
    return root, snapshot


def test_c_primary_graph_uses_shared_skill_and_exact_source(tmp_path, monkeypatch):
    from domain.capture import capture
    from domain.records import Records
    from domain.static_layers import Project, dependencies, symbols, calls
    from domain.structural_analysis import analyze_dependencies
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient,'import_json',lambda *a:None)
    monkeypatch.setattr(GraphClient,'check',lambda *a:None)
    repository=tmp_path/'source';repository.mkdir()
    (repository/'a.c').write_text('void start(void) { init(); }')
    (repository/'b.c').write_text('void init(void) { start(); }')
    manifest=capture(repository,tmp_path/'evidence',configuration())
    assert set(manifest['modules'])=={'a.c','b.c'}
    folder=tmp_path/'evidence/snapshots'/manifest['id']
    sources=json.loads((folder/'sources.json').read_text())
    known={n['id']:n for n in json.loads((folder/'nodes.json').read_text())}
    project=Project(sources,manifest['modules']);record=Records(sources,'dependencies','*',known)
    dependencies(record,project);graph=record.finish()
    baseline,_=analyze_dependencies(manifest,list(known.values()),graph['edges'],graph['evidence'],max_dsm_modules=300)
    assert baseline['strongly_connected_cycles']==[['a.c','b.c']]
    record=Records(sources,'symbols','*',known);symbols(record,project)
    known.update(record.known)
    record=Records(sources,'calls','*',known);calls(record,project)
    assert len(record.finish()['edges'])==2


def test_static_artifacts_whole_function_support_and_hostile_text(tmp_path):
    from domain.static_analysis import build, source_context
    from domain.catalog_contract import load_snapshot
    from domain.catalog_store import CatalogStore
    sources={'a.c':'// </script><script>throw 1</script>\nvoid start(void) { init(); }',
             'b.c':'void init(void) { }'}
    root,_=captured(tmp_path,sources);cfg=configuration()
    refs=build(block_context({'run_dir':root,'config':cfg}))
    assert all((root/ref['path']).exists() for ref in refs)
    store=CatalogStore(root)
    query,evidence=source_context(store,load_snapshot(root),{'kind':'aspect_analysis','aspect_id':'AR-02-01'},'start')
    assert query['rows'][0]['candidate_callees']==['b.c::init']
    assert len(query['rows'][0]['source_evidence_ids'])==2
    assert all(e['excerpt'] in sources[e['path']] for e in evidence)
    html=(root/'web/code-map.html').read_text()
    assert '</script><script>throw 1' not in html
    assert "connect-src 'self'" in html and 'map-data' not in html
    assert store.read('data/function-evolution.json')['status']=='unavailable'
    assert build(block_context({'run_dir':root,'config':cfg}))==refs
    (root/'data/static-code.json').write_text('{}')
    with pytest.raises(RuntimeError,match='different content'):
        build(block_context({'run_dir':root,'config':cfg}))


def test_focused_plan_has_no_inventory_model_scans_and_preserves_phase_barriers(tmp_path,monkeypatch):
    from domain.static_analysis import build
    from native_test_support import initializer, planner
    from domain.catalog_store import CatalogStore
    from native_test_support import publish
    from handoff_test_support import review_task
    from test_catalog_review import fake
    monkeypatch.setenv('MN_WORKFLOW_RUN_ID','focused-fixture')
    monkeypatch.setenv('MN_JOB_SHARED_STORAGE_ROOT',str(tmp_path/'submission'))
    monkeypatch.setattr('domain.catalog_planning.prepare_gateway',lambda _: {'api_base':'http://gateway:4000/v1','model':'default','catalog_id':'fixture','node':'fixture'})
    cfg=configuration();cfg['offline']=False;cfg['text_memory']['enabled']=False
    root,_=captured(tmp_path,{'core.c':'int helper(void) { return 1; }\nint run(void) { return helper(); }'})
    context={'run_dir':root,'config':cfg,'payload':{'goal':'Explain components and function changes'},
             'output_folder':str(tmp_path/'delivery')}
    build(block_context(context))
    value,_=initializer(context);ref=value['context'];store=CatalogStore(root)
    plan=store.load_ref(store.read('catalog/context.json')['plan'])
    assert len(plan['tasks'])==19
    assert len(plan['omitted']['unselected_aspects'])==144
    assert not any(t['kind']=='source_scan' for t in plan['tasks'])
    seen=[]
    for revision in range(21):
        result=planner(context,{'context':ref,'_child':{'revision':revision}})['child_plan']
        if result['decision']=='stop':break
        assert len(result['steps'])<=2
        assert all(node['needs']==[] for node in result['steps'])
        for node in result['steps']:
            task=store.load_ref(node['input']['task']);seen.append(task['kind'])
            if task['kind']=='aspect_challenge':
                assert 'analysis-'+task['aspect_id'] in store.results()
            review_task(context,ref,{'id':node['id'],**node['input']},fake)
    else:pytest.fail('Focused review failed to finish')
    assert seen[-1]=='executive_synthesis'
    publish(context)
    report=store.read('data/report.json')
    assert report['scope']['review_profile']=='focused'
    assert len(report['coverage'])==150
    assert sum(r['coverage']=='not_analyzed' for r in report['coverage'])==144
    assert all('selected focused review' in r['applicability_reason'] for r in report['coverage'] if r['coverage']=='not_analyzed')
    assert (tmp_path/'delivery/web/code-map.html').exists()
    assert (root/'web/code-map.html').exists()
    assert 'Graph evolution' in (root/'web/assets/report-shell.js').read_text()
    assert (root/'web/index.html').read_bytes() == (root/'web/code-map.html').read_bytes()
    assert (root/'web/assets/graph-evolution.js').is_file()
    assert (root/'web/assets/code-paths.js').is_file()
    assert (root/'web/assets/comparison-presentation.js').is_file()
    assert 'comparison-presentation.js?v=' in (root/'web/index.html').read_text()
    for asset in ('report-shell.js','report-shell.css'):
        assert (root/'web/assets'/asset).is_file()
        assert asset+'?v=' in (root/'web/index.html').read_text()
    assert 'workspace.json' in (root/'web/review-register.html').read_text()
    assert '../web/maps/' in (root/'reports/report.md').read_text()


def test_source_context_stale_snapshot_rejected(tmp_path):
    from domain.static_analysis import build, source_context
    from domain.catalog_contract import load_snapshot
    from domain.catalog_store import CatalogStore
    root,_=captured(tmp_path,{'a.c':'void a(void) {}'})
    build(block_context({'run_dir':root,'config':configuration()}))
    snapshot=load_snapshot(root);snapshot['snapshot_id']='other'
    with pytest.raises(ValueError,match='snapshot changed'):
        source_context(CatalogStore(root),snapshot,{},'a')


def test_markdown_file_identity_cannot_break_its_table_or_code_span():
    from domain.code_map import _code
    value=_code('path`with|newline\n.c')
    assert value.startswith('`` ') and value.endswith(' ``')
    assert '\n' not in value and '&#124;' in value


def test_refreshed_shell_invalidates_changed_browser_assets(tmp_path, monkeypatch):
    from domain import code_map
    assets = tmp_path / 'workspace_assets'
    assets.mkdir()
    (assets/'code-map.html').write_text('<link href="@ASSETS@/map.css"><script src="@ASSETS@/map.js"></script>')
    (assets/'map.css').write_text('body { color: black; }')
    (assets/'map.js').write_text('"old";')
    monkeypatch.setattr(code_map, '__file__', str(tmp_path/'code_map.py'))
    first = code_map.render(assets='../assets')
    (assets/'map.js').write_text('"new";')
    second = code_map.render(assets='../assets')
    assert first.split('<script')[0] == second.split('<script')[0]
    assert first.split('<script')[1] != second.split('<script')[1]
    assert '?v='+hashlib.sha256(b'"new";').hexdigest()[:12] in second
    assert '../assets/map.js' in second


def test_replaying_an_older_run_cannot_replace_the_latest_code_map(tmp_path):
    from test_workspace_output import fixture
    from domain.workspace_web import publish
    def prepare(run, marker):
        context,workspace=fixture(tmp_path,run=run)
        (Path(context['run_dir'])/'reports/code-map.md').write_text('[Map](../web/code-map.html)')
        for filename in ('static-code.json','function-evolution.json'):
            (Path(context['run_dir'])/'data'/filename).write_text(marker)
        return context,workspace
    first,one=prepare('first-map','first-map-data');publish(block_context(first),{}, {},workspace=one, review_file=(first).get('payload', {}).get('review_file'))
    retained=Path(first['job_data_dir'])/'architecture_results'
    (retained/'web/maps'/f"{one['id']}.html").write_text('obsolete template')
    second,two=prepare('second-map','second-map-data');publish(block_context(second),{}, {},workspace=two, review_file=(second).get('payload', {}).get('review_file'))
    assert 'tab-overview' in (retained/'web/maps'/f"{one['id']}.html").read_text()
    publish(block_context(first),{}, {},workspace=one, review_file=(first).get('payload', {}).get('review_file'))
    root=Path(first['job_data_dir'])/'architecture_results'
    assert '../data/snapshots/'+two['id'] in (root/'web/code-map.html').read_text()
    assert (root/'data/snapshots'/one['id']/'static-code.json').read_text()=='first-map-data'
    assert (root/'data/snapshots'/two['id']/'static-code.json').read_text()=='second-map-data'
    assert '../../../web/maps/'+one['id']+'.html' in (root/'reports/snapshots'/one['id']/'code-map.md').read_text()
    assert not list((root/'web').rglob('*.json'))
    for name in ('vendor/vercel-brand.css', 'vendor/Geist-Variable.woff2',
                 'vendor/GeistMono-Variable.woff2', 'vendor/geist-LICENSE.txt', 'report-fonts.css'):
        assert (root/'web/assets'/name).is_file()
    for shell in (root/'web/maps'/f"{one['id']}.html", root/'web/index.html'):
        text=shell.read_text()
        assert 'report-components.css?v=' in text and 'report-fonts.css?v=' in text
    assert not list((root/'data').rglob('*.md'))
    assert '../reviews/'+one['id']+'.html' in (root/'web/maps'/f"{one['id']}.html").read_text()
    assert '../../data/snapshots/'+one['id'] in (root/'web/reviews'/f"{one['id']}.html").read_text()


def test_provider_failures_stop_spending_and_publish_static_review(tmp_path, monkeypatch):
    from domain.static_analysis import build
    from native_test_support import initializer, planner
    from native_test_support import publish
    from domain.catalog_store import CatalogStore
    from handoff_test_support import review_task
    monkeypatch.setenv('MN_WORKFLOW_RUN_ID','provider-fail-fixture')
    monkeypatch.setenv('MN_JOB_SHARED_STORAGE_ROOT',str(tmp_path/'submission'))
    monkeypatch.setattr('domain.catalog_planning.prepare_gateway',lambda _: {'api_base':'http://gateway:4000/v1','model':'default','catalog_id':'fixture','node':'fixture'})
    cfg=configuration();cfg['offline']=False;cfg['text_memory']['enabled']=False
    root,_=captured(tmp_path,{'core.c':'int run(void) { return 1; }'})
    ctx={'run_dir':root,'config':cfg,'payload':{'goal':'Explain code growth'}}
    build(block_context(ctx));value,_=initializer(ctx);ref=value['context']
    decision=planner(ctx,{'context':ref,'_child':{'revision':0}})
    def failed(prompt):
        task=json.loads(prompt)['task']
        return json.dumps({'task_id':task['task_id'],'kind':task['kind'],'status':'blocked',
            'reason':'OpenCode reported an error event; inspect provider/tool setup'})
    for node in decision['child_plan']['steps']:
        review_task(ctx,ref,{'id':node['id'],**node['input']},failed)
    terminal=planner(ctx,{'context':ref,'_child':{'revision':1}})['child_plan']
    assert terminal['decision']=='stop'
    publish(ctx);store=CatalogStore(root);report=store.read('data/report.json')
    assert report['terminal']['usage']['catalog_models']==2
    assert report['review_health']['provider_errors']==2
    assert 'Static analysis extracted 1 named functions' in report['executive']
    assert len(store.read('data/verification_tasks.json'))==6
    assert len(report['scope']['unselected_aspects'])==144
    assert not list((root/'web').rglob('*.md'))


def test_history_budget_exhaustion_keeps_current_facts_and_explicit_unknown(tmp_path, monkeypatch):
    from domain.static_analysis import build
    from domain.catalog_contract import load_snapshot
    from domain.catalog_store import CatalogStore
    from mn_static_code_analysis_skill.history import HistoryLimitError
    root,_=captured(tmp_path,{'core.c':'int run(void) { return 1; }'})
    snapshot=load_snapshot(root);snapshot['manifest']['repository']=str(tmp_path)
    def exceeded(*args,**kwargs):raise HistoryLimitError('History timeline fact limit exceeded')
    monkeypatch.setattr('domain.static_analysis.analyze_history',exceeded)
    build(block_context({'run_dir':root,'config':configuration()}),snapshot)
    store=CatalogStore(root)
    assert len(store.read('data/static-code.json')['functions'])==1
    history=store.read('data/function-evolution.json')
    assert history['status']=='unavailable' and 'fact limit' in history['reason']
    assert history['events']==[] and 'unknown' in history['limitations'][0]


def test_stated_scope_status_excludes_unselected_catalog_topics():
    from domain.catalog_reporting import review_status
    rows=[{'aspect_id':'selected','coverage':'complete_for_stated_scope'},
          {'aspect_id':'outside','coverage':'not_analyzed'}]
    assert review_status(rows,['outside'],{'status':'completed'},{'pending_task_ids':[]})=='review_draft'
    assert review_status(rows,[],{'status':'completed'},{'pending_task_ids':[]})=='partial'
    assert review_status(rows,['outside'],{'status':'completed'},{'pending_task_ids':['challenge']})=='partial'


def test_capture_and_static_publication_include_rust_and_node_module_variants(tmp_path, monkeypatch):
    from domain.capture import capture
    from domain.static_analysis import build
    from mn_graph_analysis_skill import GraphClient
    monkeypatch.setattr(GraphClient,'import_json',lambda *a:None)
    monkeypatch.setattr(GraphClient,'check',lambda *a:None)
    repository=tmp_path/'source';repository.mkdir()
    sources={'lib.rs':'mod util; fn run() { util::helper(); }','util.rs':'pub fn helper() {}',
      'main.mts':'import {helper} from "./helper.js"; export function run() { return helper(); }',
      'helper.ts':'export function helper() { return 1; }'}
    for name,text in sources.items():(repository/name).write_text(text)
    cfg=configuration();root=tmp_path/'run'
    manifest=capture(repository,root/'evidence',cfg)
    (root/'snapshot.json').write_text(json.dumps(manifest))
    assert set(manifest['sources'])==set(sources)
    refs=build(block_context({'run_dir':root,'config':cfg}))
    facts=json.loads((root/'data/static-code.json').read_text())
    assert {'rust','typescript'} <= facts['language_coverage'].keys()
    assert {'lib.rs::run','main.mts::run'} <= {f['id'] for f in facts['functions']}
    assert ('main.mts','helper.ts','import') in {(e['source'],e['target'],e['kind']) for e in facts['component_edges']}
    score=json.loads((root/'data/architecture-score.json').read_text())
    assert score['snapshot_id']==manifest['id'] and score['maximum']==100
    assert score['dimensions'][-1]['points'] is None
    assert all((root/ref['path']).exists() for ref in refs)


def test_static_only_capture_does_not_dispatch_unnecessary_review_workers(tmp_path, monkeypatch):
    from domain.static_analysis import build
    from native_test_support import initializer, planner
    from native_test_support import publish
    from domain.catalog_store import CatalogStore
    cfg=configuration();cfg['text_memory']['enabled']=False;cfg['offline']=True
    root,_=captured(tmp_path,{'core.c':'int run(void) { return 1; }'})
    ctx={'run_dir':root,'config':cfg,'payload':{'goal':'Inspect the static graph'}}
    def forbidden(*args,**kwargs):pytest.fail('Static-only review must not admit a sandbox/model task')
    monkeypatch.setattr('domain.review_admission.admit',forbidden)
    monkeypatch.setattr('domain.catalog_planning.prepare_gateway',forbidden)
    build(block_context(ctx));value,_=initializer(ctx);work={'context':value['context'],'_child':{'revision':0}}
    decision=planner(ctx,work)
    assert decision['child_plan']['decision']=='stop'
    assert planner(ctx,work)==decision
    store=CatalogStore(root)
    assert store.usage()['catalog_models']==0 and not store.path('catalog/admissions').exists()
    assert len(store.read('catalog/terminal.json')['pending_task_ids'])==19
    publish(ctx)
    report=store.read('data/report.json')
    assert report['status']=='partial' and not report['findings']
    assert all(r['coverage']=='not_analyzed' for r in report['coverage'])
    assert 'Static-only capture requested' in report['terminal']['stop_reason']


def test_static_witnesses_seed_graph_scope_before_retrieval_even_without_memory(tmp_path, monkeypatch):
    from domain.static_analysis import build, source_context
    from domain.catalog_contract import load_snapshot, load_catalog
    from domain.catalog_store import CatalogStore
    from domain.catalog_retrieval import retrieve
    from domain.context_query_plan import plan
    sources={'src/entry.c':'void entry(void) { helper(); }',
      'src/helper.c':'void helper(void) { finish(); }','src/finish.c':'void finish(void) {}',
      'tests/test_cycles.py':'def circular_dependency_cycle():\n return 1\n'}
    root,manifest=captured(tmp_path,sources);cfg=configuration();cfg['text_memory']['enabled']=False
    manifest['modules']={p:{'path':p} for p in sources}
    (root/'snapshot.json').write_text(json.dumps(manifest))
    build(block_context({'run_dir':root,'config':cfg}));store=CatalogStore(root);snapshot=load_snapshot(root)
    task={'task_id':'analysis-AR-04-02','kind':'aspect_analysis','aspect_id':'AR-04-02'}
    captured_seeds=[]
    def graph(store,snapshot,task,focus,config,evidence,request):
        decision=plan(task,focus,snapshot['manifest']['modules'],evidence,config)
        captured_seeds.extend(decision['modules'])
        assert 'entity_unresolved' not in decision['unresolved']
        return {'status':'queried','queries':[],'incomplete':False},[]
    monkeypatch.setattr('domain.catalog_retrieval.graph_context',graph)
    monkeypatch.setattr('domain.catalog_retrieval.source_context',lambda *args:({'status':'disabled'},[]))
    saved={'request':{'retrieval_config':cfg,'goal':'Explain the component graph and recommend tests',
                      'memory_scope':{'job_id':'fixture','run_id':'fixture'}}}
    context,evidence=retrieve(store,saved,snapshot,task,load_catalog())
    assert len(captured_seeds)>=3 and all(p.startswith('src/') for p in captured_seeds[:3])
    assert context['architecture_graph']['status']=='queried' and evidence
    rows=context['architecture_graph']['queries'][0]['rows']
    assert len({row['function'].split('::')[0] for row in rows[:3]})==3
    assert any(row['candidate_callees'] for row in rows)
    query,_=source_context(store,snapshot,task,'Tests and coverage')
    assert query['rows'][0]['function'].startswith('tests/')


def test_focused_review_challenges_measured_cycles_before_broad_mapping(tmp_path, monkeypatch):
    from domain.static_analysis import build
    from native_test_support import initializer, planner
    cfg=configuration();cfg['text_memory']['enabled']=False;cfg['catalog_review']['tasks_per_round']=1
    root,_=captured(tmp_path,{'a.c':'void a(void) { b(); }','b.c':'void b(void) { a(); }'})
    ctx={'run_dir':root,'config':cfg,'payload':{'goal':'Understand the architecture'}}
    monkeypatch.setattr('domain.review_admission.admit',lambda *args,**kwargs:{'fixture':'frozen-input'})
    build(block_context(ctx));value,_=initializer(ctx,llm_client=lambda _:None)
    decision=planner(ctx,{'context':value['context'],'_child':{'revision':0}})
    assert decision['child_plan']['steps'][0]['id']=='analysis-AR-04-02'
