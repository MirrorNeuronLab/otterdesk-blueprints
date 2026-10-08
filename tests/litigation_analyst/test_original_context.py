import hashlib
import json
import pytest

from test_litigation_analyst import modules, make_context, graph_engine_stub


def test_original_search_is_separate_and_complete_with_exact_character_citations(modules, tmp_path, text_memory_transport):
    from domain.intake import PreparedCorpus
    from domain.source_query import search
    folder=tmp_path/'input'; folder.mkdir()
    text='Notice café🙂. 1. Approval requires consent unless an emergency exists. 2. Routine duties continue.'
    (folder/'contract.txt').write_text(text)
    context=make_context(tmp_path,folder); modules['intake'].prepare_sources(context)
    root=context['run_dir']; manifest=json.loads((root/'case/source-query.json').read_text())
    scope=manifest['binding']['scope']
    assert scope=={'job_id':'test-memory-job','run_id':'test-memory-run'}
    reference=next(iter(manifest['source_records'].values()))
    assert reference['scope']['job_id']!=scope['job_id']
    assert not text_memory_transport.scopes.get(('test-memory-job','test-memory-run'), {})
    corpus=PreparedCorpus(root/'case','case')
    result=search(root/'case',corpus,context['config'],scope,'approval consent',1)
    span=result['passages'][0]
    assert span['text']=='1. Approval requires consent unless an emergency exists. '
    assert text[span['start_offset']:span['end_offset']]==span['text']
    assert span['content_sha256']==hashlib.sha256(text.encode()).hexdigest()
    assert result['retrieval']=='membrane_original_source_units' and not result['exhaustive']
    puts=len([call for call in text_memory_transport.calls if call[0]=='put'])
    assert search(root/'case',corpus,context['config'],scope,'approval consent',1)==result
    assert len([call for call in text_memory_transport.calls if call[0]=='put'])==puts
    with pytest.raises(ValueError,match='binding'):
        search(root/'case',corpus,context['config'],{**scope,'run_id':'other'},'approval',1)
    # The local frozen manifest cannot hide canonical source tampering.
    text_memory_transport.scopes[(reference['scope']['job_id'],None)][reference['source_id']]='changed'
    with pytest.raises(ValueError,match='changed'):
        search(root/'case',corpus,context['config'],scope,'approval',1)


def test_32kb_runtime_allowance_does_not_reserve_all_required_evidence_room(modules):
    from domain.round_model import evidence_room
    frozen={'config':{'context_memory':{'policy':{'window_tokens':32768,'output_tokens':768}},
                      'text_memory':{'enabled':True,'max_context_bytes':32768}},
            'payload':{'goal':'Assess approval and counterevidence.'}}
    schema={'type':'object','properties':{'decision':{'type':'string'}}}
    assert evidence_room(frozen,'assess','Keep qualifications.',{'evidence':[]},schema)>1000


def test_assessor_can_read_multiple_whole_units_while_finding_citations_stay_bounded(modules, tmp_path, monkeypatch):
    from domain import round_tasks
    from domain.round_state import initialize
    from domain.evidence.store import EvidenceStore
    from domain.app.findings import submit_report
    folder=tmp_path/'input';folder.mkdir()
    approval='Approval requires written consent. '+ 'Qualified recorded context. '*45
    counter='Routine duties provide an ordinary explanation. '+ 'No identity conclusion is established. '*35
    (folder/'contract.txt').write_text('1. '+approval+' 2. '+counter)
    context=make_context(tmp_path,folder)
    modules['intake'].prepare_sources(context);modules['indexing'].build_indexes(context)
    result,_=initialize(context);ref=result['context']
    from domain.round_state import save,read
    task={'prefix':'large-comparison','hypothesis':{'id':'H01','question':'Compare approval and routine duties.',
        'support_query':'approval','counter_query':'routine','graph_tools':[],
        'expected_information':'Read both complete explanations.'}}
    task_ref=save(context['run_dir'],'case/rounds/large-task.json',task)
    work={'context':ref,'task':task_ref}
    round_tasks.collect_evidence(context,work)
    monkeypatch.setattr(round_tasks,'evidence_room',lambda *args:10000)
    seen=[]
    def decision(root,frozen,key,stage,instruction,data,schema,client):
        seen.extend(data['evidence'])
        assert sum(len(e['text'].encode()) for e in data['evidence'])>2000
        assert approval in data['evidence'][0]['text'] and counter in data['evidence'][1]['text']
        assert '2000 UTF-8 bytes' in instruction
        return {'hypothesis':{'id':'H01','question':task['hypothesis']['question'],
            'factual_basis':'Two complete recorded explanations are visible.',
            'supporting_evidence':[data['evidence'][0]['evidence_id']],
            'contradictory_evidence':[data['evidence'][1]['evidence_id']],
            'alternatives':['Routine duties.'],'status':'inconclusive','assessment':'Identity remains unverified.',
            'outstanding_enquiries':['Verify surrounding context.'],'parent_id':None},
            'report':{'findings':[],'conclusion_ids':[],'follow_up':[]}}
    monkeypatch.setattr(round_tasks,'complete',decision)
    round_tasks.assess_hypothesis(context,work)
    frozen=read(context['run_dir']/ref['path'])
    proposal={'findings':[{'id':'finding','section':'findings','title':'Bounded claim',
        'assessment':'Unverified interpretation.','evidence_ids':[e['evidence_id'] for e in seen],
        'limitations':'Authenticity unverified.'}],'conclusion_ids':['finding'],'follow_up':[]}
    with pytest.raises(ValueError,match='at most 2000'):
        submit_report({},proposal,EvidenceStore(context['run_dir']/'case/evidence.sqlite3'),frozen['investigation_id'])
