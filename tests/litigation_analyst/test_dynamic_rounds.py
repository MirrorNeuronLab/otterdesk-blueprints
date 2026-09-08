import json
import importlib
import pytest
from test_litigation_analyst import modules, graph_engine_stub, make_context, BLUEPRINT


class RoundModel:
    model = 'scripted-rounds'
    def __init__(self):
        self.calls = []
    def completion_text(self, system, user):
        data = json.loads(user)
        self.calls.append(data)
        if data['stage'] == 'plan':
            r = data['revision']
            if r == 2:
                return json.dumps({'decision':'stop','rationale':'Two enquiries completed; identity remains for human review.','hypotheses':[]})
            if r:
                assert data['prior_findings'][0]['outstanding_enquiries']
            return json.dumps({'decision':'execute','rationale':'Test the notice and ordinary explanations.','hypotheses':[{
                'id':'H01','question':'Does the notice establish approval?',
                'support_query':'approval' if not r else 'notice', 'counter_query':'routine',
                'graph_tools':[], 'expected_information':'Distinguish approval from routine correspondence.'}]})
        if data['stage'] == 'assess':
            ids = [e['evidence_id'] for e in data['evidence']]
            return json.dumps({'hypothesis':{'id':'H01','question':'Does the notice establish approval?',
                'factual_basis':'The supplied notice mentions approval.','supporting_evidence':ids,'contradictory_evidence':[],
                'alternatives':['Routine duties explain the notice.'],'status':'inconclusive','assessment':'The notice alone cannot establish identity.',
                'outstanding_enquiries':['Verify identity and surrounding correspondence.'],'parent_id':None},
                'report':{'findings':[{'id':data['finding_id'],'section':'findings','title':'Approval notice',
                'assessment':'The notice mentions approval; identity remains unresolved.','evidence_ids':ids,
                'limitations':'Ranked retrieval is incomplete.'}], 'conclusion_ids':[data['finding_id']], 'follow_up':['Verify identity.']}})
        assert data['stage'] == 'review'
        assert data['evidence']
        return json.dumps({'accepted_ids':[f['id'] for f in data['report']['findings']], 'issues':['Authenticity remains unverified.']})


@pytest.fixture
def dynamic_case(modules, tmp_path):
    from domain.round_state import initialize
    folder=tmp_path/'input'; folder.mkdir()
    (folder/'notice.txt').write_text('Approval notice. Routine duties explain the correspondence.')
    context=make_context(tmp_path,folder)
    modules['intake'].prepare_sources(context); modules['indexing'].build_indexes(context)
    output,_=initialize(context)
    return context, output['context']


def execute_round(context, ref, result, model):
    from domain import round_tasks
    handlers={'collect_litigation_evidence':round_tasks.collect_evidence,
        'assess_litigation_hypothesis':round_tasks.assess_hypothesis,
        'review_litigation_finding':round_tasks.review_finding,
        'summarize_litigation_round':round_tasks.summarize_round}
    done=set()
    for node in result['child_plan']['steps']:
        assert set(node['needs']) <= done
        output=handlers[node['template']](context,{'context':ref,**node['input'],'_child':{}},llm_client=model)
        assert len(json.dumps(output)) < 1000
        done.add(node['id'])


def test_default_child_workflow_replans_and_publishes_reviewed_evidence(dynamic_case, modules):
    from domain.round_planning import plan_round
    context,ref=dynamic_case; model=RoundModel()
    first=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=model)
    execute_round(context,ref,first,model)
    second=plan_round(context,{'context':ref,'_child':{'revision':1}},llm_client=model)
    assert first != second
    execute_round(context,ref,second,model)
    stopped=plan_round(context,{'context':ref,'_child':{'revision':2}},llm_client=model)
    assert stopped['child_plan']['decision']=='stop'
    count=len(model.calls)
    assert plan_round(context,{'context':ref,'_child':{'revision':2}},llm_client=model)==stopped
    execute_round(context,ref,second,model)
    assert len(model.calls)==count
    modules['reporting'].write_review(context)
    text=(context['run_dir']/'final_report.md').read_text()
    assert 'Approval notice' in text and 'Authenticity remains unverified' in text
    state=json.loads((context['run_dir']/'case/agent_checkpoint.json').read_text())
    assert state['mode']=='dynamic_subworkflow'
    assert len(state['records'])==4
    assert state['data']['hypotheses']['H01']['status']=='inconclusive'
    assert state['data']['report_review']['accepted_ids']==['r02-H01']
    assert (context['run_dir']/'case/rounds/r01-H01-assessment.json').exists()


def test_cancel_before_planning_writes_explicit_partial_draft(dynamic_case, modules):
    from domain.round_planning import plan_round
    context,ref=dynamic_case
    (context['run_dir']/'case/cancel.request').touch()
    model=RoundModel()
    result=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=model)
    assert result['child_plan']['output']['stop_reason']=='cancelled'
    assert model.calls==[]
    modules['reporting'].write_review(context)
    assert 'cancelled' in (context['run_dir']/'final_report.md').read_text()


def test_task_hash_and_graph_mutations_are_rejected(dynamic_case):
    from domain.round_planning import plan_round
    from domain.round_tasks import collect_evidence, validate_graph_query
    context,ref=dynamic_case
    result=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=RoundModel())
    node=result['child_plan']['steps'][0]
    (context['run_dir']/node['input']['task']['path']).write_text('{}')
    with pytest.raises(ValueError,match='hash'):
        collect_evidence(context,{'context':ref,**node['input']})
    for q in ('MATCH (n) DELETE n RETURN n LIMIT 2','MATCH (n) RETURN n','MATCH (n) RETURN n LIMIT 51'):
        with pytest.raises(ValueError): validate_graph_query(q)


def test_autonomous_explorer_preserved_but_not_default(modules):
    source=(BLUEPRINT/'payloads/agents/litigation_investigator.py').read_text()
    assert 'round_state import initialize' in source
    assert callable(importlib.import_module('domain.app.agentic').run_investigation)
    assert callable(modules['research'].investigate)
    workflow=json.loads((BLUEPRINT/'workflow.json').read_text())
    child=workflow['child_workflows']['investigate_case_evidence']
    assert child['planner']=='plan_litigation_round'
    assert child['max_rounds']==3 and len(child['templates'])==5


def test_reviewer_rejection_withholds_dynamic_finding(dynamic_case, modules):
    from domain.round_planning import plan_round
    context,ref=dynamic_case
    class Rejecting(RoundModel):
        def completion_text(self, system, user):
            if json.loads(user)['stage']=='review':
                return json.dumps({'accepted_ids':[], 'issues':['Claim requires more context.']})
            return super().completion_text(system,user)
    model=Rejecting()
    first=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=model)
    execute_round(context,ref,first,model)
    (context['run_dir']/'case/cancel.request').touch()
    plan_round(context,{'context':ref,'_child':{'revision':1}},llm_client=model)
    modules['reporting'].write_review(context)
    text=(context['run_dir']/'final_report.md').read_text()
    assert 'No reviewed principal conclusion' in text
    assert 'Claim requires more context.' in text
    assert '### Approval notice' not in text


def test_dynamic_assessment_rejects_invented_evidence(dynamic_case):
    from domain.round_planning import plan_round
    from domain.round_tasks import collect_evidence, assess_hypothesis
    context,ref=dynamic_case
    class Inventing(RoundModel):
        def completion_text(self, system, user):
            value=json.loads(super().completion_text(system,user))
            if json.loads(user)['stage']=='assess': value['hypothesis']['supporting_evidence']=['invented']
            return json.dumps(value)
    model=Inventing()
    first=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=model)
    work={'context':ref,**first['child_plan']['steps'][0]['input']}
    collect_evidence(context,work)
    with pytest.raises(ValueError,match='unavailable evidence'):
        assess_hypothesis(context,work,llm_client=model)


def test_review_schema_accepts_finding_ids_only(dynamic_case, monkeypatch):
    from domain.round_planning import plan_round
    from domain import round_tasks
    context,ref=dynamic_case; model=RoundModel()
    result=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=model)
    work={'context':ref,**result['child_plan']['steps'][0]['input']}
    round_tasks.collect_evidence(context,work)
    round_tasks.assess_hypothesis(context,work,llm_client=model)
    def review(root,frozen,key,stage,instruction,data,schema,client):
        assert schema['properties']['accepted_ids']['items']=={'enum':['r01-H01']}
        assert 'NEVER evidence or source IDs' in instruction
        return {'accepted_ids':['r01-H01'],'issues':[]}
    monkeypatch.setattr(round_tasks,'complete',review)
    round_tasks.review_finding(context,work,llm_client=model)


def test_partial_collection_preserves_completed_actions(dynamic_case,monkeypatch):
    from domain.round_planning import plan_round
    from domain import round_tasks
    context,ref=dynamic_case
    result=plan_round(context,{'context':ref,'_child':{'revision':0}},llm_client=RoundModel())
    work={'context':ref,**result['child_plan']['steps'][0]['input']}
    original=round_tasks.observe_action; calls=[]
    def fail_second(action,state,execute):
        calls.append(action)
        if len(calls)==2: raise RuntimeError('test transport failure')
        return original(action,state,execute)
    monkeypatch.setattr(round_tasks,'observe_action',fail_second)
    with pytest.raises(RuntimeError,match='test transport failure'):
        round_tasks.collect_evidence(context,work)
    paths=sorted((context['run_dir']/'case/rounds/actions').glob('*.json'))
    assert len(paths)==2
    assert json.loads(paths[0].read_text())['result']['passages']
    assert json.loads(paths[1].read_text())['result']['error']=='test transport failure'
