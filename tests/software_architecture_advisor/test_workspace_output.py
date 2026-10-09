"""Data-grounded output, cumulative Job storage, exact drill-through and unsafe-source tests."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import pytest


def fixture(tmp_path, *, run='first', body='from beta import pay\n', job='job-one',
            include_finding=False, exclude=None, model='test-provider'):
    from domain.workspace_projection import project
    root = tmp_path / run
    sources = {'src/checkout/a.py': body, 'src/payments/b.py': 'def pay():\n    return 1\n'}
    source_id = run.replace('-', '')
    records = {p: {'text': s, 'sha256': hashlib.sha256(s.encode()).hexdigest()} for p, s in sources.items()}
    manifest = {'id': source_id, 'repository_id': 'actual-repo-identity', 'git_anchor': 'a'*40,
        'sources': {p: r['sha256'] for p, r in records.items()},
        'modules': {'checkout.a': {'path':'src/checkout/a.py'}, 'payments.b': {'path':'src/payments/b.py'}},
        'ingest_config': {'exclude': exclude or ['node_modules']}, 'coverage': {'source_files':2}}
    directory = root / 'evidence/snapshots' / source_id
    directory.mkdir(parents=True)
    (directory / 'sources.json').write_text(json.dumps(records))
    (root / 'snapshot.json').write_text(json.dumps(manifest))
    (root / 'analysis').mkdir()
    (root / 'analysis/dependencies.json').write_text(json.dumps({
        'modules':['checkout.a','payments.b'], 'dependencies':[{'source':'checkout.a','target':'payments.b',
        'source_locations':[{'path':'src/checkout/a.py','sha256':records['src/checkout/a.py']['sha256'],'line_start':1,'line_end':1}]}]}))
    (root / 'report.md').write_text('# Actual report\n')
    (root / 'report.json').write_text('{}')
    report = {'analysis_started':'2026-10-08T14:30:00+00:00', 'input':{}, 'goal':'Review payment boundaries',
        'status':'partial','executive':'Evidence still needed','terminal':{'stop_reason':'budget'},
        'scope':{'capture_limits':{},'exclusions':['node_modules']}}
    registers = {'evidence':[], 'findings':[], 'claims':[], 'recommendations':[], 'work_packages':[],
        'verification_tasks':[], 'coverage':{'aspects':[]}, 'assumptions':[]}
    if include_finding:
        # A source fact for review workflow tests; not an architectural defect.
        registers['evidence'] = [{'id':'fixed-evidence-id', 'path':'src/checkout/a.py',
            'sha256':records['src/checkout/a.py']['sha256'], 'start_line':1, 'end_line':1,
            'excerpt':body.splitlines(keepends=True)[0]}]
        registers['findings'] = [{'id':'source-fact', 'statement':'The module imports payment code',
            'aspect_ids':['01'], 'evidence_ids':['fixed-evidence-id'], 'counterevidence_ids':[],
            'confidence':'medium', 'confidence_rationale':'Captured source import', 'status':'provisional'}]
    context = {'run_dir':root, 'run_id':run, 'job_id':job, 'job_data_dir':tmp_path/job,
        'config':{'opencode':{'model':model}, 'outputs':{'folder_path':str(tmp_path/run/'delivery')}}, 'payload':{}}
    return context, project(context, report, registers)


def test_projection_uses_real_captured_source_and_rejects_bad_edge(tmp_path):
    from domain.workspace_projection import project
    ctx, workspace = fixture(tmp_path)
    assert len(workspace['relations']) == 1
    source = workspace['evidence'][0]
    assert source['excerpt'] == 'from beta import pay\n'
    assert source['revision'] == 'a'*40
    assert workspace['relations'][0]['basis'] == 'candidate static'
    assert workspace['components'][0]['basis'] == 'inferred directory grouping'
    path = ctx['run_dir'] / 'analysis/dependencies.json'
    value = json.loads(path.read_text())
    value['dependencies'][0]['source_locations'][0]['sha256'] = 'bad'
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='source does not match'):
        # Only fields consumed by this invalid projection need a minimal report.
        project(ctx, {'analysis_started':'now'}, {'evidence':[]})


def test_cochange_exact_sets_and_asymmetric_denominators(tmp_path):
    from domain.workspace_projection import cochange
    _, workspace = fixture(tmp_path)
    a,b = [c['id'] for c in workspace['components']]
    left,right = workspace['components'][0]['files'][0],workspace['components'][1]['files'][0]
    commits = [{'id':str(i),'at':'2026-10-08','paths':[left,right] if i<12 else [left] if i<20 else [right] if i<24 else []} for i in range(40)]
    workspace['history'] = {'status':'available','change_sets':commits}
    result = cochange(workspace,a,b)
    assert (result['shared'],result['left'],result['right'],result['union']) == (12,20,16,24)
    assert (result['right_given_left'],result['left_given_right'],result['jaccard']) == (.6,.75,.5)
    assert {c['id'] for c in result['matching']} == {str(i) for i in range(12)}
    commits[0]['mechanical'] = True
    assert cochange(workspace,a,b,exclude_mechanical=True)['shared'] == 11
    workspace['history'] = {'status':'unavailable','reason':'No Git','change_sets':None}
    assert cochange(workspace,a,b)['status'] == 'unavailable'


def test_job_snapshots_accumulate_and_earlier_replay_cannot_roll_back_latest(tmp_path):
    from domain.workspace_history import retain
    first_ctx, first = fixture(tmp_path)
    one, index, root = retain(first_ctx,first)
    first_bytes = (root/'data/snapshots'/one['id']/'workspace.json').read_bytes()
    second_ctx, second = fixture(tmp_path,run='second',body='from beta import pay\n# changed\n')
    two,index,_ = retain(second_ctx,second)
    assert len(index['snapshots']) == 2
    assert index['latest'] == two['id']
    assert two['changes']['files'][0]['path'] == 'src/checkout/a.py'
    assert (root/'data/snapshots'/one['id']/'workspace.json').read_bytes() == first_bytes
    again,index,_ = retain(first_ctx,first)
    assert again == one and len(index['snapshots']) == 2 and index['latest'] == two['id']
    assert json.loads((root/'data/workspace.json').read_text())['id'] == two['id']
    other_ctx, other = fixture(tmp_path,run='third',job='job-two')
    _,other_index,other_root = retain(other_ctx,other)
    assert other_root != root and len(other_index['snapshots']) == 1
    changed = deepcopy(first); changed['executive'] = 'altered'
    with pytest.raises(ValueError,match='changed on replay'):
        retain(first_ctx,changed)


def test_comparison_paths_keep_baseline_citations_and_unknown_behavior(tmp_path):
    from domain.workspace_projection import compare
    _,one=fixture(tmp_path)
    _,two=fixture(tmp_path,run='second',body='from beta import pay\n# new\n')
    two['files'][1]['sha256']='changed-provider'
    two['relations']=[]  # A removed candidate import still has baseline dependency context.
    result=compare(two,one)
    assert result['baseline_definition'].startswith('Previous retained')
    assert result['impacts'][0]['dependent_path']=='src/checkout/a.py'
    assert result['impacts'][0]['behavior'].startswith('Unknown')
    assert result['baseline_evidence']
    two['scope_identity']='changed'
    assert not compare(two,one)['scope_comparable']


def test_review_import_preserves_attribution_and_requires_reassessment(tmp_path):
    from domain.workspace_history import apply_reviews
    _,workspace=fixture(tmp_path)
    f={'continuity_key':'stable','material_digest':'m1','review_history':[],'review_state':'Awaiting review'}
    workspace['findings']=[f]
    row={'id':'r1','continuity_key':'stable','material_digest':'m1','actor':'Engineer','at':'2026-10-08T14:30:00Z','rationale':'Guard reviewed','action':'Dismiss'}
    source={'schema_version':'mn.architecture.reviews.v1','repository_id':workspace['repository_id'],'decisions':[row]}
    apply_reviews(workspace,source)
    assert f['review_state']=='Dismiss'
    apply_reviews(workspace,source)
    assert len(f['review_history'])==1
    with pytest.raises(ValueError,match='Immutable review changed'):
        apply_reviews(workspace,{**source,'decisions':[{**row,'rationale':'rewritten'}]})
    f['material_digest']='m2'
    apply_reviews(workspace,source)
    assert f['review_state']=='Needs reassessment'
    with pytest.raises(ValueError,match='repository'):
        apply_reviews(workspace,{**source,'repository_id':'wrong'})
    with pytest.raises(ValueError,match='schema'):
        apply_reviews(workspace,[])


def test_render_real_records_safely_and_publish_required_web_handle(tmp_path, monkeypatch):
    from domain.workspace_web import render
    from domain.workspace_history import retain
    ctx,w=fixture(tmp_path,body='value = "</script><script>alert(1)</script>"\n')
    w,index,root=retain(ctx,w)
    page=render(w,index)
    assert 'connect-src &#x27;none&#x27;' in page
    assert '</script><script>alert(1)' not in page
    assert '\\u003c/script>' in page
    assert 'ATLAS_DATA' not in page and 'SYNTHETIC DEMO' not in page
    assert 'script-src &#x27;sha256-' in page


def test_sdk_host_delivery_places_data_web_at_job_root(tmp_path):
    from mn_sdk.blueprint_support.shared_outputs import materialize_shared_storage_outputs
    host=tmp_path/'shared'; submission=host/'submissions/job'; source=submission/'outputs/runs/runone'
    source.mkdir(parents=True)
    (source/'report.md').write_text('run report')
    (source/'data').mkdir(); (source/'data/index.json').write_text('{}')
    (source/'web').mkdir(); (source/'web/index.html').write_text('<html>Actual data</html>')
    target=tmp_path/'Downloads/software_architecture_advisor'
    storage={'host_root':str(host),'runtime_root':'/runtime/shared','host_submission_path':str(submission),'run_id':'runone',
        'output_copy':[{'source_path':'/runtime/shared/submissions/job/outputs/runs/runone','target_path':str(target),'layout':'batch','job_files':['data','web']}]}
    result=materialize_shared_storage_outputs(storage,publish_results=False)
    assert not result['errors']
    assert (target/'data/index.json').exists() and (target/'web/index.html').exists()
    run_folder=next(target.glob('run_*'))
    assert (run_folder/'report.md').exists()
    assert not (run_folder/'data').exists() and not (run_folder/'web').exists()


def test_web_failure_is_explicit_after_durable_data_and_success_has_valid_handle(tmp_path, monkeypatch):
    from domain import workspace_web
    ctx,w=fixture(tmp_path)
    monkeypatch.setattr(workspace_web,'project',lambda *args: deepcopy(w))
    real_render=workspace_web.render
    def broken(*args,**kwargs):
        raise OSError('Cannot render dashboard')
    monkeypatch.setattr(workspace_web,'render',broken)
    with pytest.raises(OSError,match='Cannot render'):
        workspace_web.publish(ctx,{}, {})
    assert (ctx['run_dir']/'data/workspace.json').exists()
    assert not (ctx['run_dir']/'web_ui.json').exists()
    monkeypatch.setattr(workspace_web,'render',real_render)
    result,refs=workspace_web.publish(ctx,{}, {})
    assert all((ctx['run_dir']/ref['path']).is_file() for ref in refs)
    handle=json.loads((ctx['run_dir']/'web_ui.json').read_text())
    assert handle['adapter']=='static_html'
    assert Path(handle['path'])==ctx['run_dir']/'web/index.html'
    assert len(json.loads((ctx['run_dir']/'data/index.json').read_text())['snapshots'])==1


def test_replayed_page_handle_and_public_contract_stay_bound_to_latest_snapshot(tmp_path, monkeypatch):
    from domain import workspace_web
    ctx, first = fixture(tmp_path)
    second_ctx, second = fixture(tmp_path, run='second', body='from beta import pay\n# new\n')
    monkeypatch.setattr(workspace_web, 'project', lambda context, *_: deepcopy(first if context is ctx else second))
    workspace_web.publish(ctx, {}, {})
    workspace_web.publish(second_ctx, {}, {})
    result, refs = workspace_web.publish(ctx, {}, {})
    latest = json.loads((ctx['run_dir']/'data/workspace.json').read_text())
    handle = json.loads((ctx['run_dir']/'web_ui.json').read_text())
    assert handle['metadata']['snapshot'] == latest['snapshot_id'] == second['snapshot_id']
    assert next(r['path'] for r in refs if r['kind']=='architecture_workspace') == 'data/workspace.json'
    assert result['snapshot'] == first['id']
    assert json.loads((ctx['run_dir']/result['data']['path']).read_text())['id'] == first['id']


def test_review_material_binds_source_scope_and_model_but_not_delivery_folders(tmp_path):
    from domain.workspace_history import retain
    ctx, first = fixture(tmp_path, include_finding=True)
    f = first['findings'][0]
    f['review_history'] = [{'id':'r1', 'continuity_key':f['continuity_key'], 'material_digest':f['material_digest'],
        'actor':'Engineer', 'at':'2026-10-08T14:30:00Z', 'rationale':'Inspected import', 'action':'Dismiss'}]
    f['review_state'] = 'Dismiss'
    retain(ctx, first)
    ctx, identical = fixture(tmp_path, run='second', include_finding=True)
    saved, _, _ = retain(ctx, identical)
    assert saved['changes']['analysis_comparable'] and saved['findings'][0]['review_state'] == 'Dismiss'
    ctx, new_source = fixture(tmp_path, run='third', include_finding=True, body='from beta import pay\n# new context\n')
    saved, _, _ = retain(ctx, new_source)
    assert saved['findings'][0]['review_state'] == 'Needs reassessment'
    ctx, new_scope = fixture(tmp_path, run='fourth', include_finding=True, body='from beta import pay\n# new context\n', exclude=['tests'])
    saved, _, _ = retain(ctx, new_scope)
    assert not saved['changes']['scope_comparable'] and saved['findings'][0]['review_state'] == 'Needs reassessment'
    ctx, new_model = fixture(tmp_path, run='fifth', include_finding=True, body='from beta import pay\n# new context\n', exclude=['tests'], model='other-model')
    saved, _, _ = retain(ctx, new_model)
    assert not saved['changes']['analysis_comparable'] and saved['findings'][0]['review_state'] == 'Needs reassessment'


def test_model_finding_annotations_are_bounded_and_source_linked(tmp_path):
    from domain.review_response import validate_result
    from domain.review_prompts import output_shape
    shape = output_shape({'task_id':'scan', 'kind':'source_scan'}, ())
    assert 'architecture' in shape['claims'][0]
    assert 'architecture' not in shape['observations'][0]
    ctx,w=fixture(tmp_path)
    e=w['evidence'][0]
    citation={k:e[k] for k in ('path','sha256','start_line','end_line','excerpt')}
    citation.update(start_offset=0,end_offset=len(e['excerpt']))
    details={field:'Source-backed scenario; runtime remains unknown' for field in
        ('question','capability','mechanism','consequence','priority_rationale','next_decision','closure_condition')}
    claim={'claim_id':'C1','statement':'A module imports payment code','rationale':'Captured import span',
        'counterevidence':'Runtime execution unavailable','counterevidence_status':'unknown',
        'counterevidence_citations':[],'claim_type':'observed','confidence':'medium','finding':True,
        'evidence':[citation],'architecture':details}
    value={'task_id':'scan','kind':'source_scan','status':'completed','conclusion':'Scoped import review',
        'scope':'Two source files','limitations':['No runtime evidence'],'claims':[claim],'observations':[]}
    snapshot={'sources':{e['path']:{'text':e['excerpt'],'sha256':e['sha256']}}}
    assert validate_result({'task_id':'scan','kind':'source_scan'},value,snapshot,{})['claims'][0]['architecture']==details
    claim['architecture']['mechanism']='x'*2001
    with pytest.raises(ValueError,match='architecture.mechanism'):
        validate_result({'task_id':'scan','kind':'source_scan'},value,snapshot,{})


def test_disappeared_finding_and_changed_scope_are_not_verified_resolution(tmp_path):
    from domain.workspace_projection import compare
    _,previous=fixture(tmp_path)
    _,current=fixture(tmp_path,run='second')
    previous['findings']=[{'id':'old','continuity_key':'prior'}]
    current['scope_identity']='different'
    result=compare(current,previous)
    assert result['findings'][0]['kind']=='No longer evaluated'
    assert result['findings'][0]['note'].startswith('Not verified resolved')
    assert not result['scope_comparable']


def handoff_workspace(tmp_path):
    _, w = fixture(tmp_path, include_finding=True)
    f = w['findings'][0]
    f.update(status='supported', claim_ids=['claim-one'], counterevidence='Existing guards may make a refactor unnecessary.',
             counterevidence_status='unknown')
    w['claims'] = [{'id':'claim-one', 'evidence_ids':f['evidence_ids'], 'counterevidence_ids':[]}]
    w['recommendations'] = [{'id':'recommendation-one', 'finding_ids':[f['id']], 'claim_ids':['claim-one'],
        'action':'Review the payment boundary', 'impact':'Make boundary changes easier to review; benefit unmeasured.',
        'alternatives':'Keep the existing import or introduce a narrow interface.', 'success_conditions':'Payment behavior stays unchanged.'}]
    w['work_packages'] = [{'id':'package-one', 'recommendation_ids':['recommendation-one'],
        'goal':'Introduce a narrow payment interface if justified', 'evidence_ids':f['evidence_ids'],
        'files':['src/checkout/a.py','src/payments/b.py'], 'verification_required':False,
        'constraints':'Preserve payment behavior.', 'non_goals':'No service split or database migration.',
        'migration_steps':'Review callers, introduce the interface, then update the import.',
        'required_tests':'Exercise existing payment behavior and relevant import callers.',
        'acceptance':'Payment behavior stays unchanged.', 'stop_conditions':'Stop if the premise is contradicted.'}]
    return w


def test_coding_handoff_preserves_scope_counterevidence_and_exact_sources(tmp_path):
    from domain.improvement_prompts import build, markdown
    w = handoff_workspace(tmp_path)
    before = deepcopy(w)
    data = build(w)
    assert w == before and build(w) == data
    rows = [p for p in data['prompts'] if p['record_type']=='work_package']
    assert {p['mode'] for p in rows} == {'Plan','Implement','Verify'}
    implementation = next(p for p in rows if p['mode']=='Implement')
    body = implementation['prompt']
    assert w['evidence'][0]['sha256'] in body and 'from beta import pay' in body
    assert 'Existing guards may make a refactor unnecessary.' in body
    assert 'No service split or database migration.' in body and 'Payment behavior stays unchanged.' in body
    assert 'preserve unrelated work' in body and 'not a measured outcome' in body
    assert implementation['target_files'] == ['src/checkout/a.py','src/payments/b.py']
    w['improvement_prompts'] = data
    doc = markdown(w)
    assert all(p['prompt'].rstrip() in doc for p in rows)


def test_unresolved_work_never_generates_implementation_and_large_support_stays_whole(tmp_path):
    from domain.improvement_prompts import build, MAX_BYTES
    w = handoff_workspace(tmp_path)
    w['findings'][0]['status'] = 'contested'
    assert not any(p['mode']=='Implement' for p in build(w)['prompts'])
    w['findings'][0]['status'] = 'supported'
    w['work_packages'][0]['verification_required'] = True
    assert not any(p['mode']=='Implement' for p in build(w)['prompts'])
    w['work_packages'][0]['verification_required'] = False
    w['evidence'][0]['excerpt'] = '# é' * 30000
    data = build(w)
    assert not any(p['mode']=='Implement' for p in data['prompts'])
    assert any(p['omitted_source_records'] for p in data['prompts'])
    assert len({p['id'] for p in data['prompts']}) == len(data['prompts'])
    assert all(len(p['prompt'].encode()) <= MAX_BYTES for p in data['prompts'])
    assert all('# é' not in p['prompt'] for p in data['prompts'])


def test_static_cycle_handoff_requests_investigation_without_fabricated_remediation(tmp_path):
    from domain.improvement_prompts import build
    _, w = fixture(tmp_path)
    w['cycles'] = [['checkout.a','payments.b']]
    data = build(w)
    cycle = next(p for p in data['prompts'] if p['record_type']=='cycle')
    assert cycle['mode'] == 'Investigate'
    assert 'A cycle alone does not establish a defect' in cycle['prompt']
    assert cycle['evidence_ids'] == w['relations'][0]['evidence_ids']
    assert not any(p['mode']=='Implement' for p in data['prompts'])


def test_main_report_and_retained_dashboard_share_identical_coding_prompts(tmp_path, monkeypatch):
    from domain import catalog_publication
    from domain.improvement_prompts import build
    ctx, w = fixture(tmp_path)
    rich = handoff_workspace(tmp_path/'handoff')
    # Keep the same source baseline while exercising the actual publication boundary.
    rich.update(id=w['id'], snapshot_id=w['snapshot_id'], run_id=w['run_id'])
    rich['improvement_prompts'] = build(rich)
    report = {'sections':[], 'status':'partial', 'snapshot':w['snapshot_id'], 'executive':'Source review only',
        'scope':{'reviewed_source_packets':1,'source_packets':1}, 'terminal':{'stop_reason':'test'},
        'authorization':'No automatic source changes.'}
    files = {k:rich[k] for k in ('claims','evidence','findings','recommendations','assumptions','work_packages')}
    files.update(coverage=rich['coverage'], verification_tasks=[], roadmap={})
    monkeypatch.setattr(catalog_publication,'assemble',lambda _: (deepcopy(report),deepcopy(files),{}))
    monkeypatch.setattr(catalog_publication,'project',lambda *_: deepcopy(rich))
    (ctx['run_dir']/'report.json').unlink()
    (ctx['run_dir']/'report.md').unlink()
    catalog_publication.publish(ctx)
    root = ctx['run_dir']
    implementation = next(p for p in rich['improvement_prompts']['prompts'] if p['mode']=='Implement')
    assert implementation['prompt'].rstrip() in (root/'report.md').read_text()
    assert implementation['prompt'].rstrip() in (root/'work_packages/package-one.md').read_text()
    retained = root/'data/snapshots'/rich['id']
    assert implementation['prompt'].rstrip() in (retained/'improvement_prompts.md').read_text()
    assert json.loads((root/'improvement_prompts.json').read_text()) == rich['improvement_prompts']
    assert json.loads((root/'report.json').read_text())['improvement_prompts'] == rich['improvement_prompts']
    assert json.loads((retained/'workspace.json').read_text())['improvement_prompts'] == rich['improvement_prompts']
    assert catalog_publication.publish(ctx)[0]['status'] == 'partial'
