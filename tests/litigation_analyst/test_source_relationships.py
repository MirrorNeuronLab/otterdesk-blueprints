import json

from test_litigation_analyst import modules, make_context


def test_legal_clause_keeps_continuations_definitions_and_cross_references(modules):
    from domain.legal_sources import LegalSourceAdapter
    from mn_context_engine_sdk.intelligent_system.sources import dependency_closure
    text = ('1. Definitions. “Emergency” means immediate danger.\n\n'
            '2. Approval. Written approval is required.\n\nExcept in an Emergency under Section 3.\n\n'
            '3. Exception. Notice must follow within one day.\n\n4. Unrelated. Addresses.')
    adapter=LegalSourceAdapter(); sections=adapter.sections(text,'agreement.txt')
    root=next(s for s in sections if '2. Approval.' in text.encode()[s.start_byte:s.end_byte].decode())
    closure=dependency_closure(sections,[root])
    content=''.join(text.encode()[s.start_byte:s.end_byte].decode() for s in closure)
    assert 'Except in an Emergency' in content and 'means immediate danger' in content
    assert 'Notice must follow' in content and '4. Unrelated' not in content


def test_source_dependency_group_cannot_admit_only_the_main_clause(modules):
    from domain.evidence_admission import admit
    spans=[{'evidence_id':'main','text':'approval'}, {'evidence_id':'exception','text':'x'*6000}]
    records=[{'result':{'support_groups':[{'id':'qualified','source_evidence_ids':['main','exception'],
                                         'required':False,'complete':True}]}}]
    assert admit(spans,records,1024)['evidence']==[]
    assert len(admit(spans,records,8192)['evidence'])==2


def test_independent_review_preserves_dependencies_and_coverage(modules):
    from domain.evidence_admission import review_closure, coverage
    spans=[{'evidence_id':'main'}, {'evidence_id':'exception'}, {'evidence_id':'unrelated'}]
    records=[{'purpose':'support', 'result':{'status':'incomplete',
        'unresolved':['external_reference'], 'passages':spans,
        'support_groups':[{'id':'qualified','source_evidence_ids':['main','exception'],'complete':True}]}}]
    support=review_closure(spans,records,{'main'})
    assert {s['evidence_id'] for s in support} == {'main','exception'}
    assert coverage(records,{'main'})[0]['unresolved'] == ['external_reference']


def test_hybrid_index_is_cited_revision_bound_and_replayed_without_inference(modules,tmp_path):
    from domain.relationship_index import build
    from domain.intake import PreparedCorpus
    folder=tmp_path/'input'; folder.mkdir()
    (folder/'contract.txt').write_text('1. Approval requires written notice.')
    context=make_context(tmp_path,folder); modules['intake'].prepare_sources(context)
    context['config']['source_relationships']['mode']='hybrid'
    class Model:
        model='fixture'; model_revision='sha256:fixture'; calls=0
        def completion_text(self,system,user):
            self.calls += 1
            request=json.loads(user)
            assert 'runtime_memory' not in request
            return json.dumps({'statements':[{'predicate':'OBLIGATION','subject':'Approval',
                'object':'written notice','quote':'Approval requires written notice.'}], 'references':[]})
    model=Model(); corpus=PreparedCorpus(context['run_dir']/'case','case')
    first=build(context,corpus.scan(),llm_client=model)
    assert first['proposals'][0]['kind']=='model_proposal'
    assert first['proposals'][0]['quote']=='Approval requires written notice.'
    assert build(context,corpus.scan(),llm_client=model)==first and model.calls==1
    assert first['units'][0]['file_id'] and first['units'][0]['revision']


def test_invented_extraction_quote_remains_incomplete(modules,tmp_path):
    from domain.relationship_index import build
    from domain.intake import PreparedCorpus
    folder=tmp_path/'input'; folder.mkdir(); (folder/'c.txt').write_text('Approval is conditional.')
    context=make_context(tmp_path,folder); modules['intake'].prepare_sources(context)
    context['config']['source_relationships']['mode']='hybrid'
    class Model:
        model='fixture'
        def completion_text(self,*args):
            return json.dumps({'statements':[{'predicate':'OBLIGATION','subject':'x','object':'y',
                'quote':'invented statement'}], 'references':[]})
    result=build(context,PreparedCorpus(context['run_dir']/'case','case').scan(),llm_client=Model())
    assert not result['complete'] and not result['proposals']
    assert result['coverage'][0]['unresolved'][0]['status']=='extraction_failed'


def test_native_clause_walk_hydrates_original_qualification_chain(modules,tmp_path,monkeypatch):
    from domain.relationship_index import build
    from domain.intake import PreparedCorpus
    from domain import source_graph
    folder=tmp_path/'input'; folder.mkdir()
    text='1. Approval is required, except as stated in Section 2.\n\n2. Emergencies permit later notice.'
    (folder/'contract.txt').write_text(text)
    context=make_context(tmp_path,folder); modules['intake'].prepare_sources(context)
    case=context['run_dir']/'case'; corpus=PreparedCorpus(case,'case')
    index=build(context,corpus.scan())
    root=index['units'][0]
    class Graph:
        def __init__(self,*args,**kwargs): pass
        def query(self,query,params):
            return {'rows':[{'source':r['source'],'target':r['target'],'relation':r['relation']}
                for r in index['relations'] if r['source'] in params['frontier']
                and r['relation'] in params['relations']]}
    monkeypatch.setattr(source_graph,'GraphClient',Graph)
    result=source_graph.walk(case,corpus,[root],'clause_dependencies',context['config'])
    assert [p['text'] for p in result['passages']] == [u['text'] for u in index['units']]
    assert all(text[p['start_offset']:p['end_offset']]==p['text'] for p in result['passages'])
    assert result['paths'][0]['edges'][0]['kind']=='observed_structure'
    assert result['support_groups'][0]['complete']
    assert not result['exhaustive'] and 'relationship_index_incomplete' in result['unresolved']
