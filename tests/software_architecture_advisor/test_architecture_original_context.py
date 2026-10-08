"""Architecture source authority, static code units and authored review boundaries."""
import copy
import hashlib
import json

import pytest


def setup(tmp_path, sources):
    from domain.catalog_sources import publish_inputs
    from domain.catalog_store import CatalogStore
    store = CatalogStore(tmp_path)
    snapshot = {'snapshot_id':'frozen','sources':{path:{'text':text,
        'sha256':hashlib.sha256(text.encode()).hexdigest()} for path,text in sources.items()}}
    request = {'memory_scope':{'job_id':'test-memory-job','run_id':'test-memory-run'},
               'retrieval_config':{'text_memory':{'enabled':True,'max_results':6,'max_context_bytes':32768}}}
    publish_inputs(store,request,snapshot)
    return store,request,snapshot


def test_originals_are_complete_separate_and_restore_static_units(tmp_path,text_memory_transport):
    from domain.catalog_sources import source_context
    text = 'import os\n'*200+'# 中🙂\n@decorator\ndef task_label(task):\n    return "exact label"\n'
    store,request,snapshot = setup(tmp_path,{'domain/planning.py':text})
    packet,evidence = source_context(store,request,snapshot,{'task_id':'needle'},
        'Find implementation of task_label in domain/planning.py')
    assert packet['status']=='ready' and len(evidence)==1
    assert evidence[0]['excerpt']=='@decorator\ndef task_label(task):\n    return "exact label"\n'
    assert evidence[0]['start_line']==202 and evidence[0]['end_line']==204
    assert evidence[0]['sha256']==snapshot['sources']['domain/planning.py']['sha256']
    assert any(text==body for files in text_memory_transport.scopes.values() for body in files.values())
    assert not text_memory_transport.scopes.get(('test-memory-job','test-memory-run'))
    compiled_before=sum(c[0]=='compile' for c in text_memory_transport.calls)
    assert source_context(store,request,snapshot,{'task_id':'needle'},
        'Find implementation of task_label in domain/planning.py')==(packet,evidence)
    assert sum(c[0]=='compile' for c in text_memory_transport.calls)==compiled_before


def test_syntax_unavailable_original_is_preserved_with_explicit_raw_limit(tmp_path):
    from domain.catalog_sources import source_context
    store,request,snapshot=setup(tmp_path,{'broken.py':'def invalid(:\n    return missing\n'})
    saved=store.read('catalog/source-inputs.json')
    assert saved['limitations']==[{'path':'broken.py','status':'syntax_unavailable','mode':'structural_text_units'}]
    assert saved['catalog']['sources'][0]['sections']
    packet,evidence=source_context(store,request,snapshot,{'task_id':'broken'},'Find invalid in broken.py')
    assert packet['limitations']==saved['limitations']
    assert all(e['excerpt'] in snapshot['sources']['broken.py']['text'] for e in evidence)


@pytest.mark.parametrize('enabled', [False, True])
def test_empty_source_corpus_never_reports_complete_evidence(tmp_path, enabled):
    from domain.catalog_sources import source_context
    store,request,snapshot=setup(tmp_path,{})
    request['retrieval_config']['text_memory']['quality_verification']=enabled
    packet,evidence=source_context(store,request,snapshot,{'task_id':'empty'},'Find missing')
    assert packet['status']==('incomplete' if enabled else 'not_found_in_searched_scope')
    if enabled:
        assert packet['quality']['action']=='insufficient_evidence'
    else:
        assert 'quality' not in packet
    assert packet['incomplete'] and evidence==[]


def test_final_source_gate_requires_opt_in_and_does_not_gate_synthesis():
    from domain.review_prompts import build_prompt
    def prepare(kind, config):
        return build_prompt({'task_id':'check','kind':kind,'aspect_id':'AR-test'},
            {'specs':{},'conventions':''},{'snapshot_id':'s','sources':{}},{},{},8192,{},
            quality_config=config,retrieval={'source_query':{'quality':{'repair_attempted':True}}})
    assert 'context_quality' not in prepare('aspect_analysis',{})
    config={'text_memory':{'quality_verification':True}}
    prepared=prepare('aspect_analysis',config)
    assert prepared['context_quality']['action']=='insufficient_evidence'
    assert prepared['context_quality']['retrieval']['repair_attempted']
    assert 'repair_attempted' not in prepared['prompt']
    assert prepare('executive_synthesis',config)['context_quality']['action']=='omit'


def test_named_code_query_keeps_local_helpers_constants_and_lexical_scope(tmp_path,text_memory_transport):
    from domain.catalog_sources import source_context
    text = 'LIMIT = 3\n\ndef helper(n):\n    return n > LIMIT\n\ndef unrelated():\n    return "noise"\n\ndef check(n):\n    return helper(n)\n'
    store,request,snapshot=setup(tmp_path,{'checks.py':text})
    packet,evidence=source_context(store,request,snapshot,{'task_id':'check'},'Find implementation of check in checks.py')
    assert packet['status']=='ready' and not packet['incomplete']
    content='\n'.join(e['excerpt'] for e in evidence)
    assert 'LIMIT = 3' in content and 'def helper(n)' in content and 'def check(n)' in content
    assert 'def unrelated' not in content
    assert all(e['excerpt'] in text for e in evidence)


def test_cached_original_query_rejects_changed_revision(tmp_path,text_memory_transport):
    from domain.catalog_sources import source_context
    store,request,snapshot=setup(tmp_path,{'x.py':'def exact():\n    return True\n'})
    source_context(store,request,snapshot,{'task_id':'needle'},'Find exact in x.py')
    catalog=store.read('catalog/source-inputs.json')['catalog']
    physical_scope=tuple(catalog['scope'][:2])
    id=catalog['sources'][0]['source_id']
    text_memory_transport.scopes[(physical_scope[0],None)][id]='Changed original'
    with pytest.raises(ValueError,match='stale'):
        source_context(store,request,snapshot,{'task_id':'needle'},'Find exact in x.py')


def test_runtime_knowledge_keeps_claims_and_source_locators_without_original_excerpts():
    from domain.catalog_knowledge import runtime_result
    result={'task_id':'review','kind':'aspect_analysis','status':'completed','aspect_id':'AR-01-01',
        'conclusion':'Qualified conclusion | 中🙂 '*200,'limitations':['Runtime unknown'],
        'claims':[{'claim_id':'C','statement':'Observed call','evidence':[{
            'path':'x.py','sha256':'h','start_offset':0,'end_offset':11,'excerpt':'PRIVATE_SOURCE'}],
            'counterevidence_status':'unknown','counterevidence_citations':[]}], 'observations':[]}
    original=copy.deepcopy(result)
    record=runtime_result(result,'snapshot','2026-10-04T00:00:00Z')
    assert result==original
    assert 'PRIVATE_SOURCE' not in record.markdown() and 'start_offset' in record.markdown()
    details={json.loads(line[2:-2].split(' | ')[0]):json.loads(line[2:-2].split(' | ')[1])
             for line in record.notes.splitlines() if line.startswith('| "')}
    assert details['conclusion']==result['conclusion']
    assert details['claims'][0]['statement']=='Observed call'
    assert details['claims'][0]['counterevidence_status']=='unknown'


@pytest.mark.parametrize('budget',[8192,32768])
def test_original_evidence_precedes_whole_runtime_navigation_and_does_not_mutate_packet(budget):
    from domain.review_prompts import build_prompt
    source='def exact():\n    return True\n'
    witness={'id':'S-original','path':'x.py','sha256':hashlib.sha256(source.encode()).hexdigest(),
        'start_offset':0,'end_offset':len(source),'start_line':1,'end_line':2,'excerpt':source}
    memory={'status':'ready','evidence':[{'citation':'m1','content':'Long qualified navigation '*2000}],
            'incomplete':False,'omitted_count':0}
    original=copy.deepcopy(memory)
    value=build_prompt({'task_id':'summary','kind':'executive_synthesis'},
        {'specs':{},'conventions':''},{'snapshot_id':'s','sources':{}},{},{},budget,{},
        retrieval={'runtime_memory':memory},graph_evidence=[witness])
    prompt=json.loads(value['prompt'])
    assert prompt['evidence']==[witness]
    assert prompt['runtime_memory']['status']=='insufficient_capacity'
    assert prompt['runtime_memory']['omitted_count']==1
    assert len(value['prompt'].encode())<=budget and memory==original


@pytest.mark.parametrize('budget',[8192,32768])
def test_complete_original_can_use_remaining_prompt_space_beyond_fixed_one_third(budget):
    from domain.review_prompts import build_prompt
    source='def exact():\n    return "'+'x'*2800+'"\n'
    witness={'id':'S-original','path':'x.py','sha256':hashlib.sha256(source.encode()).hexdigest(),
        'start_offset':0,'end_offset':len(source),'start_line':1,'end_line':2,'excerpt':source}
    value=build_prompt({'task_id':'summary','kind':'executive_synthesis'},
        {'specs':{},'conventions':''},{'snapshot_id':'s','sources':{}},{},{},budget,{},
        graph_evidence=[witness])
    assert json.loads(value['prompt'])['evidence']==[witness]
    assert len(value['prompt'].encode())<=budget


def test_prompt_admission_does_not_remove_rows_from_frozen_graph_packet():
    from domain.review_prompts import build_prompt
    retrieval={'architecture_graph':{'queries':[{'rows':[{'source_evidence_ids':['S-unavailable']}],
        'rows_omitted':0}],'status':'queried','incomplete':True}}
    frozen=copy.deepcopy(retrieval)
    value=build_prompt({'task_id':'summary','kind':'executive_synthesis'},
        {'specs':{},'conventions':''},{'snapshot_id':'s','sources':{}},{},{},8192,{},
        retrieval=retrieval)
    assert not json.loads(value['prompt'])['architecture_graph']['queries'][0]['rows']
    assert retrieval==frozen
