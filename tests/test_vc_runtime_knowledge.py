"""VC publisher and consumer policy; native engine probes own index semantics."""
import importlib
import json
from pathlib import Path

import pytest
from vc_assistant.domain_test_support import load_domain_test_surface


@pytest.fixture
def modules(text_memory_transport):
    surface = load_domain_test_surface(Path(__file__).resolve().parents[1] / 'vc_assistant')
    return surface,importlib.import_module('domain.text_memory'),importlib.import_module('domain.runtime_observations'),importlib.import_module('domain.runtime_knowledge')


def context(tmp_path,*,budget=32768):
    return {'run_dir':tmp_path,'config':{'text_memory':{'enabled':True,'max_results':6,'max_context_bytes':budget}}}


def evidence(tmp_path,*,unknown=False):
    directory = tmp_path/'workflow_state/company_evidence'
    directory.mkdir(parents=True)
    value = {
        'source_records':[
            {'source_id':'S-founder','source_type':'founder_provided_document','status':'ok','retrieval_status':'full_text',
             'source_quality_label':'local_claim','retrieved_at':'' if unknown else '2026-10-03T01:00:00Z'},
            {'source_id':'S-blocked','source_type':'blocked_page','status':'blocked','retrieval_status':'full_text',
             'source_quality_label':'unavailable','retrieved_at':'2026-10-03T02:00:00Z'}],
        'evidence_items':[{'evidence_id':'E-founder','source_id':'S-founder','raw_excerpt':'PRIVATE_BODY'},
                          {'evidence_id':'E-blocked','source_id':'S-blocked','raw_excerpt':'PRIVATE_BLOCKED_BODY'}],
        'claim_records':[
            {'claim_id':'C-founder','canonical_claim':'Founder claims ARR 120000 | 中🙂',
             'claim_type':'traction.revenue.arr','value':120000,'unit':'USD_ARR','evidence_ids':['E-founder'],
             'required_next_evidence':['invoice','independent customer confirmation'],
             'verification_status':'self_reported_unverified'},
            {'claim_id':'C-counter','canonical_claim':'Independent revenue confirmation was unavailable.',
             'claim_type':'traction.revenue.arr','value':None,'evidence_ids':['E-blocked'],
             'verification_status':'unavailable'}]}
    (directory/'sample.json').write_text(json.dumps(value))
    return value


def trace(tmp_path,*,unknown=False):
    events = [{'type':'observability_operation_failed' if n==4 else 'observability_operation_completed',
        'timestamp':'' if unknown and n==4 else f'2026-10-03T03:00:0{n}Z',
        'payload':{'phase':'public_tool_call','agent_id':'traction_verifier','operation_id':'tool-'+str(n),
                   'operation':'browser_page','status':'failed' if n==4 else 'completed',
                   'tool_status':'blocked' if n==4 else 'ok','error':'No independent confirmation' if n==4 else None}}
        for n in range(1,5)]
    (tmp_path/'llm_rag_trace.jsonl').write_text('\n'.join(json.dumps(event) for event in events)+'\n')


def test_markdown_preserves_conflict_source_roles_recent_three_and_external_boundary(modules,tmp_path,text_memory_transport):
    _,adapter,_,_ = modules
    evidence(tmp_path);trace(tmp_path)
    current = {'rag_context':{'context':'RAG_CANARY','citations':[{'ref':1}],'status':'ready'}}
    rendered = adapter.actor_memory_context(context(tmp_path),current,step_id='review',agent_id='traction_verifier')
    packet = rendered['runtime_memory']
    serialized = json.dumps(packet,ensure_ascii=False)
    assert packet['status']=='ready' and len(packet['evidence'])==5
    assert all(item['content'].startswith('# VC ') for item in packet['evidence'])
    for necessary in ['tool-4','tool-3','tool-2','Founder claims ARR 120000','confirmation was unavailable',
                      'self_reported_unverified','blocked_page','independent customer confirmation']:
        assert necessary in serialized
    assert 'tool-1' not in serialized
    bodies = str(text_memory_transport.scopes)
    assert 'RAG_CANARY' not in bodies and 'PRIVATE_BODY' not in bodies and 'PRIVATE_BLOCKED_BODY' not in bodies
    assert rendered['rag_context']==current['rag_context']
    assert 'fixture_witness' not in serialized
    sidecar = json.loads(next((tmp_path/'workflow_state').glob('membrane-*.json')).read_text())
    assert all(handles[0]['end_byte']>handles[0]['start_byte'] for handles in sidecar['receipt']['citations'].values())
    assert 'FROM_SOURCE' in str(text_memory_transport.scopes) and 'EVIDENCED_BY' in str(text_memory_transport.scopes)


def test_source_outcome_does_not_become_retrieval_default_confirmation(modules,tmp_path):
    _,_,observations,knowledge = modules
    evidence(tmp_path)
    records = list(observations.runtime_observations(context(tmp_path)))
    blocked = next(record for record in records if record['observation_id']=='S-blocked')
    assert blocked['status']=='blocked' and blocked['retrieval_status']=='full_text'
    counter = next(record for record in records if record['observation_id']=='C-counter')
    assert counter['source_qualifications'][0]['status']=='blocked'
    assert counter['source_qualifications'][0]['retrieval_status']=='full_text'
    blocked.update(memory_family='vc_runtime',snapshot_id='frozen')
    markdown = knowledge.authored_record(blocked,'2026-10-04T00:00:00Z').markdown()
    assert '| status |' in markdown and 'blocked' in markdown


def test_publication_clock_is_stable_unknown_event_is_not_recent(modules,tmp_path,text_memory_transport):
    _,adapter,_,_ = modules
    evidence(tmp_path,unknown=True);trace(tmp_path,unknown=True)
    ctx = context(tmp_path)
    first = adapter.actor_memory_context(ctx,{},step_id='review',agent_id='traction_verifier')
    original = {key:dict(value) for key,value in text_memory_transport.scopes.items()}
    second = adapter.actor_memory_context(ctx,{},step_id='review',agent_id='traction_verifier')
    assert first == second and text_memory_transport.scopes == original
    text = json.dumps(first['runtime_memory'])
    assert 'tool-4' in text and 'runtime_publication' in text and 'unknown' in text
    retrievals = [call[1] for call in text_memory_transport.calls if call[0]=='retrieve']
    assert retrievals[-1]['stages'][0]['analytical']['timestamp_field']=='event_timestamp'
    assert any(stage['analytical']['operation']=='rows' and any(
        f.get('field')=='event_time_status' and f.get('value')=='unknown'
        for f in stage['analytical']['filters']) for stage in retrievals[-1]['stages'])


def test_offset_and_fractional_source_times_have_real_chronological_order(modules):
    _,_,_,knowledge = modules
    assert knowledge.latest_source_timestamp([
        {'retrieved_at':'2026-10-03T03:00:00+02:00'},
        {'retrieved_at':'2026-10-03T01:00:00.500Z'},
        {'retrieved_at':'invalid'},{'retrieved_at':'2026-10-03T04:00:00'}])=='2026-10-03T01:00:00.500000Z'


def test_authored_facts_do_not_duplicate_values_or_create_absent_columns(modules):
    _,_,_,knowledge = modules
    record = {'memory_family':'vc_runtime','snapshot_id':'snapshot','kind':'claim',
        'observation_id':'C','company':'Sample','qualification':'unverified',
        'timestamp':'2026-10-03T01:00:00Z','value':None,'claim':'complete claim | 中🙂',
        'required_next_evidence':['invoice','customer']}
    authored=knowledge.authored_record(record,'2026-10-04T00:00:00Z')
    assert 'value' in authored.fields and authored.fields['value'] is None
    assert 'method_id' not in authored.fields and 'source_type' not in authored.fields
    assert '| "value" |' not in authored.notes and '| "company" |' not in authored.notes
    details={json.loads(line[2:-2].split(' | ')[0]):json.loads(line[2:-2].split(' | ')[1])
             for line in authored.notes.splitlines() if line.startswith('| "')}
    assert details['claim']==record['claim']
    assert details['required_next_evidence']==record['required_next_evidence']


def test_complete_source_claim_beyond_preview_is_extracted_without_runtime_body(modules,tmp_path,text_memory_transport):
    surface,_,_,_ = modules
    source = tmp_path/'packet.txt'
    source.write_text('Company: Sample AI\n'+'Unrelated paragraph.\n'*200+'ARR is $120000 from recurring revenue.\n')
    records = surface.scan_documents(tmp_path,{'text_memory':{'enabled':True}})['Sample AI']
    assert 'ARR' not in records[0]['text_preview']
    layer = surface.build_company_evidence_layer('Sample AI',records,[])
    assert any(claim['claim_type']=='traction.revenue.arr' and claim['value']==120000 for claim in layer['claim_records'])
    assert any(item['raw_excerpt']=='ARR is $120000 from recurring revenue.' for item in layer['evidence_items'])
    assert not text_memory_transport.scopes.get(('test-memory-job','test-memory-run'))


def test_oversized_whole_knowledge_is_explicit_capacity_not_clipped(modules,tmp_path):
    _,adapter,_,_ = modules
    value = evidence(tmp_path)
    value['claim_records'][0]['canonical_claim']='qualified claim | 中🙂 '*800
    (tmp_path/'workflow_state/company_evidence/sample.json').write_text(json.dumps(value))
    rendered = adapter.actor_memory_context(context(tmp_path,budget=8192),{},step_id='review',agent_id='reviewer')
    packet = rendered['runtime_memory']
    assert packet['incomplete'] and packet['omitted_count']==1
    assert len(json.dumps(packet,ensure_ascii=False,separators=(',',':')).encode())<=8192
    assert 'qualified claim' not in json.dumps(packet)


def test_no_runtime_observations_remains_no_evidence(modules,tmp_path):
    _,adapter,_,_ = modules
    rendered = adapter.actor_memory_context(context(tmp_path),{},step_id='review',agent_id='reviewer')
    assert rendered['runtime_memory']['status']=='no_evidence'


def test_markdown_sources_reuse_job_storage_independently_of_runtime_memory(modules,tmp_path,text_memory_transport):
    surface,_,_,_=modules
    inputs=tmp_path/'inputs';inputs.mkdir()
    document=inputs/'packet.txt'
    document.write_text('Company: Sample AI\nComplete confidential source founder@example.com.\n')
    output=tmp_path/'shared'/'context_sources'/'inputs'
    config={'source_context':{'enabled':True},'text_memory':{'enabled':False}}
    first=surface.scan_documents(inputs,config,source_output_folder=output)['Sample AI'][0]
    second=surface.scan_documents(inputs,config,source_output_folder=output)['Sample AI'][0]
    assert first['markdown_reused'] is False and second['markdown_reused'] is True
    body=(output/'packet.txt.md').read_text()
    assert '[REDACTED-EMAIL]' in body and 'founder@example.com' not in body
    catalog=json.loads((output.parent/'inputs.json').read_text())
    assert catalog['catalog']['sources'][0]['path'].endswith('.md')
    for key in ('source_id','revision','scope'):
        assert first['context_source'][key]==second['context_source'][key]
    assert not text_memory_transport.scopes.get(('test-memory-job','test-memory-run'))
    document.write_text('Company: Sample AI\nChanged source body.\n')
    changed=surface.scan_documents(inputs,config,source_output_folder=output)['Sample AI'][0]
    assert not changed['markdown_reused'] and changed['sha256']!=first['sha256']


def test_output_json_is_markdown_source_and_never_runtime_body(modules,tmp_path,text_memory_transport):
    import hashlib
    _,_,_,_=modules
    from domain.artifact_sources import index_output_artifacts
    folder=tmp_path/'shared';folder.mkdir()
    original=folder/'report.json';original.write_text('{"claim":"Complete output 中🙂"}')
    ctx={'run_dir':tmp_path/'run','output_folder':folder,
         'config':{'source_context':{'enabled':True},'text_memory':{'enabled':False}}}
    index_output_artifacts(ctx,[{'path':str(original),'kind':'report'}])
    path=folder/'context_sources/outputs/report.json.md'
    assert 'Complete output' in path.read_text()
    inventory=json.loads((folder/'context_sources/outputs.json').read_text())
    assert inventory['files'][0]['sha256']==hashlib.sha256(path.read_bytes()).hexdigest()
    assert inventory['catalog']['sources'][0]['path']=='outputs/report.json.md'
    assert not text_memory_transport.scopes.get(('test-memory-job','test-memory-run'))
