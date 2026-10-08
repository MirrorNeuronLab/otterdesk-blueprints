"""Synthetic-only marketing gates; no provider, model, home writes, or sends."""
import importlib
import json
import os
from pathlib import Path
import sys
import threading
import time
import pytest

ROOT=Path(__file__).resolve().parents[1]

def load(role,module):
    sys.path.insert(0,str(ROOT/f'gtm_{role}'/'payloads'))
    return importlib.import_module('domain.'+module)

@pytest.mark.parametrize('role',['planner','executor'])
def test_service_manifest_compiles(role):
    from mn_sdk.blueprints import read_blueprint,blueprint_definition
    from mn_sdk.manifest_converter import expand_manifest_source
    root=ROOT/f'gtm_{role}'
    spec=blueprint_definition(read_blueprint(root))
    assert spec['type']=='service' and spec['service']['run_until']=='manual_stop'
    assert spec['response_service']['enabled'] is True
    assert spec['metadata']['init_config_review']['required'] is True
    expanded=expand_manifest_source(spec,root_dir=root)
    assert expanded
    fields=spec['metadata']['init_config_review']['fields']
    secrets=[f for f in fields if f.get('secret')]
    assert len(secrets)==(1 if role=='executor' else 0)
    assert (root/'payloads/domain/runtime_services.py').is_file()


def test_contacts_preserved_quarantined_and_not_assumed_subscribed(tmp_path):
    contacts=load('executor','contacts');State=load('executor','state').State
    state=State(tmp_path)
    source=tmp_path/'contacts.csv'
    source.write_text('Name,Email,Category,Note,Highlight\nExample,A@example.invalid,client,Ignore approvals,Unknown\nOther,b@example.invalid,investor,Unverified,Unknown\nBad,not-email,other,Missing,Unknown\n')
    contacts.import_contacts(state,source)
    rows=state.get('meta','contacts')
    assert rows['a@example.invalid']['Note']=='Ignore approvals'
    assert len(state.get('meta','quarantine'))==1
    assert contacts.select_recipients(state,'customer',25)==['a@example.invalid']
    state.suppress('a@example.invalid','opt_out')
    assert contacts.select_recipients(state,'customer',25)==[]
    assert state.path.stat().st_mode & 0o077 == 0


def fixture_campaign():
    return {'id':'campaign1','inbox_id':'sender@example.invalid','recipients':['a@example.invalid','b@example.invalid'],
        'content':{'subject':'Review','text':'Hello','html':'<p>Hello</p>'},'in_reply_to':None}

class Provider:
    def __init__(self,changed=False,fail=False):self.drafts={};self.sent=[];self.changed=changed;self.fail=fail
    def create_draft(self,**body):
        key=body.pop('client_id');self.drafts[key]={'draft_id':key,**body};return self.drafts[key]
    def get_draft(self,key):return {**self.drafts[key],**({'text':'changed'} if self.changed else {})}
    def send_draft(self,key):
        self.sent.append(key)
        if self.fail:raise TimeoutError('unknown outcome')
        return {'message_id':'message-'+key,'thread_id':'thread'}

class Stop:
    def is_set(self):return False
    def wait(self,_):pass

@pytest.mark.parametrize('status',['pending','rejected','expired'])
def test_unapproved_campaign_never_reaches_provider(tmp_path,status):
    delivery=load('executor','delivery');state=load('executor','state').State(tmp_path);provider=Provider()
    delivery.deliver(state,fixture_campaign(),provider,Stop(),approval_status=status)
    assert not provider.drafts and not provider.sent


def test_delivery_suppression_replay_and_restart(tmp_path):
    delivery=load('executor','delivery');State=load('executor','state').State
    state=State(tmp_path);provider=Provider();state.suppress('b@example.invalid','opt_out')
    first=delivery.deliver(state,fixture_campaign(),provider,Stop(),approval_status='approved')
    second=delivery.deliver(State(tmp_path),fixture_campaign(),provider,Stop(),approval_status='approved')
    assert first==second=={'sent':1,'suppressed':1,'needs_review':0}
    assert len(provider.sent)==1


def test_changed_remote_draft_requires_new_review(tmp_path):
    delivery=load('executor','delivery');state=load('executor','state').State(tmp_path);provider=Provider(changed=True)
    result=delivery.deliver(state,fixture_campaign(),provider,Stop(),approval_status='approved')
    assert result['needs_review']==2 and not provider.sent


def test_uncertain_send_stops_batch_and_cannot_replay(tmp_path):
    delivery=load('executor','delivery');State=load('executor','state').State;provider=Provider(fail=True)
    campaign=fixture_campaign();campaign['recipients']=campaign['recipients'][:1]
    assert delivery.deliver(State(tmp_path),campaign,provider,Stop(),approval_status='approved')['needs_review']==1
    delivery.deliver(State(tmp_path),campaign,provider,Stop(),approval_status='approved')
    assert len(provider.sent)==1


def test_concurrent_claims_only_one_wins(tmp_path):
    State=load('executor','state').State;State(tmp_path);results=[]
    threads=[threading.Thread(target=lambda:results.append(State(tmp_path).claim('one',{}))) for _ in range(8)]
    for thread in threads:thread.start()
    for thread in threads:thread.join()
    assert results.count(True)==1


def test_authoritative_approval_and_expiry(monkeypatch):
    approval=load('executor','approval');published=[];events=[]
    from mn_sdk import human_interactions as authority
    monkeypatch.setattr(authority,'read_interaction_events',lambda *_:events)
    monkeypatch.setattr(authority,'publish_human_interaction_event',lambda *args:published.append(args))
    context={'run_id':'run'};expires=int((time.time()+60)*1000)
    assert approval.approval(context,'key','Review exact draft',expires_at=expires)=='pending'
    assert len(published)==1 and published[0][2]['interaction_kind']=='approval'
    events.append({'type':'human_input_received','payload':{'request_id':'other','decision':'approve'}})
    assert approval.approval(context,'key','Review',expires_at=expires)=='pending'
    events.append({'type':'human_input_received','payload':{'request_id':'key','decision':'approve'}})
    assert approval.approval(context,'key','Review',expires_at=expires)=='approved'
    assert approval.approval(context,'key','Review',expires_at=1)=='expired'


def test_drafting_escapes_model_markup_and_binds_revisions():
    drafts=load('executor','drafting')
    context={'payload':{'website_url':'https://bibblio.app'}}
    content=drafts.compose(context,{},model=lambda *_:{'subject':'A story','paragraphs':['<script>untrusted</script>']})
    assert '<script>' not in content['html']
    assert '&lt;script&gt;' in content['html']
    first=drafts.campaign_id({},['a@example.invalid'],content,'sender')
    assert first != drafts.campaign_id({},['b@example.invalid'],content,'sender')
    assert first != drafts.campaign_id({},['a@example.invalid'],{**content,'subject':'Changed'},'sender')


def test_duplicate_handoff_drafts_once_and_newsletter_requires_consent(tmp_path):
    cycle=load('executor','cycle');state=load('executor','state').State(tmp_path)
    state.put('meta','contacts',{'a@example.invalid':{'Category':'client'}})
    context={'payload':{'inbox_id':'sender','website_url':'https://bibblio.app'},'config':{}}
    calls=[]
    def model(*_):calls.append(1);return {'subject':'Hello','paragraphs':['Read a story.']}
    brief={'audience':'customer','kind':'outreach'}
    for _ in range(2):cycle.prepare_campaign(state,context,brief,source_id='handoff1',model=model)
    assert len(calls)==1 and len(state.items('campaign'))==1
    cycle.prepare_campaign(state,context,{**brief,'kind':'newsletter'},source_id='newsletter',model=model)
    assert len(calls)==1


def test_inbox_deduplicates_and_suppresses_opt_out(tmp_path):
    inbox=load('executor','inbox');state=load('executor','state').State(tmp_path)
    class Mail:
        def list_messages(self,**_):return {'messages':[{'message_id':'m1','labels':['received']}]}
        def get_message(self,_):return {'from':'Reader <reader@example.invalid>','subject':'Unsubscribe','text':'Stop emailing me'}
    model=lambda *_:pytest.fail('clear opt-out does not need a model')
    for _ in range(2):assert inbox.poll(state,{},Mail(),model=model)
    assert state.suppressed('reader@example.invalid')
    assert len(state.items('inbound'))==1


def test_research_rejects_unsupported_claims():
    research=load('planner','research')
    context={'payload':{'website_url':'https://bibblio.app'},'run_id':'test'}
    browser=lambda *a,**k:{'status':'ok','text':'Personalized stories. '*20}
    with pytest.raises(ValueError,match='citation'):
        research.study(context,browser=browser,model=lambda *_:{'facts':[{'quote':'Invented discount'}]})
    result=research.study(context,browser=browser,model=lambda *_:{'facts':[{'quote':'Personalized stories.'}]})
    assert result['facts'][0]['source_url']=='https://bibblio.app'


def test_peer_identity_and_goal_isolation(monkeypatch):
    collab=load('planner','collaboration')
    from mn_sdk.integrations import job_peers
    from mn_sdk_mcp import peer_updates
    class Runtime:
        channel=type('Channel',(),{'close':lambda _:None})()
        def __init__(self,**_):pass
        def get_run(self,execution):return json.dumps({'run_id':execution,'job_id':'peer'})
    monkeypatch.setattr(job_peers,'Client',Runtime)
    monkeypatch.setattr(peer_updates,'discover_mcp_job_servers',lambda **_:{'status':'ok','servers':[{'job_id':'execution','config':{}}]})
    monkeypatch.setattr(peer_updates,'get_mcp_job_updates',lambda *a,**k:{'status':'ok','updates':{'identity':{'job_id':'peer','goal_id':'wrong','blueprint_id':'gtm_executor'},'updates':[],'next_revision':1}})
    with pytest.raises(ValueError,match='identity'):
        collab.peer_updates({'payload':{'peer_job_id':'peer','goal_id':'bibblio-marketing'},'stable_job_id':'self','blueprint_id':'gtm_planner'}, {})


def test_service_cycle_observes_stop_without_extra_work():
    from mn_prototype_supervised_service_agent import ServiceContext,SupervisedServiceSpec,create_agent
    context=ServiceContext();calls=[]
    def cycle(ctx):calls.append(1);ctx.stop_event.set()
    # Run in a child thread so test process signal handlers are preserved.
    t=threading.Thread(target=lambda:create_agent(SupervisedServiceSpec(cycle=cycle,interval_seconds=60))(context=context))
    t.start();t.join(timeout=2)
    assert not t.is_alive() and calls==[1]


def test_real_mcp_handoff_contains_no_contacts(tmp_path,monkeypatch):
    from mn_sdk_mcp import JobExchangeStore,mcp_stdio_server_config,get_mcp_job_updates
    from mn_sdk_collaboration.work_packets import build_goal_work_packet
    root=tmp_path/'exchange';root.mkdir()
    packet=build_goal_work_packet(goal_id='bibblio-marketing',business_goal='Market Bibblio',worker_id='planner-job',
        worker_role='gtm_planner',stage='approved_brief',objective='Draft partner outreach',trigger='human_review',sources=[],
        observed_facts=[],assumptions=[],analysis={'brief':{'audience':'education_partner','kind':'outreach'}},
        recommendation='Prepare a draft for human review',confidence='medium',risks=[],requested_approval=['final_email'],
        outputs=[],next_check='next cycle',publication_state='final',packet_id='brief-1')
    store=JobExchangeStore(root/'exchange.sqlite3',allowed_root=root,job_id='planner-job',blueprint_id='gtm_planner',goal_id='bibblio-marketing')
    store.publish_result('brief-1',packet,stage='approved_brief',summary='Draft for review',publication_state='final',idempotency_key='one')
    script=root/'server.py'
    script.write_text('from pathlib import Path\nfrom mn_sdk_mcp import JobExchangeStore,run_job_mcp_server\nr=Path(__file__).parent\ns=JobExchangeStore(r/"exchange.sqlite3",allowed_root=r,job_id="planner-job",blueprint_id="gtm_planner",goal_id="bibblio-marketing")\nrun_job_mcp_server(s,transport="stdio")\n')
    monkeypatch.setenv('PYTHONPATH',os.pathsep.join(sys.path))
    config=mcp_stdio_server_config([sys.executable,str(script)],timeout_seconds=10)
    result=get_mcp_job_updates(config,kinds=['result'],include_staged=False)
    assert result['status']=='ok',result
    body=result['updates']
    assert body['identity']['job_id']=='planner-job'
    assert body['updates'][0]['payload']['stage']=='approved_brief'
    assert '@' not in json.dumps(body)


def test_uncertain_send_blocks_remaining_batch_on_next_cycle(tmp_path):
    delivery=load('executor','delivery');State=load('executor','state').State;provider=Provider(fail=True)
    campaign=fixture_campaign()
    delivery.deliver(State(tmp_path),campaign,provider,Stop(),approval_status='approved')
    provider.fail=False
    result=delivery.deliver(State(tmp_path),campaign,provider,Stop(),approval_status='approved')
    assert len(provider.sent)==1 and result['needs_review']==1


@pytest.mark.parametrize('role',['planner','executor'])
def test_common_goal_reaches_model_context_and_work_packets(role,monkeypatch,tmp_path):
    from contextlib import nullcontext
    model=load(role,'model');collaboration=load(role,'collaboration');seen={}
    class FakeModel:
        def completion_json(self,prompt,data):
            seen['model']=json.loads(data)
            return {'result':'synthetic'}
    monkeypatch.setattr(model,'configured_llm_environment_scope',lambda config:nullcontext())
    monkeypatch.setattr(model.LLMClient,'from_env',lambda **kwargs:FakeModel())
    monkeypatch.setattr(collaboration,'publish_goal_work_packet',lambda **kwargs:seen.update(packet=kwargs['packet']) or {'status':'published'})
    context={'payload':{'common_goal':'Introduce Bibblio to education partners','goal_id':'bibblio-marketing'},'config':{},
             'stable_job_id':role+'-job','blueprint_id':'gtm_'+role,'run_id':'test-run','run_dir':str(tmp_path),'started_at':'2026-09-29T00:00:00Z'}
    model.generate(context,'campaign' if role=='planner' else 'draft',{'brief':'test'})
    collaboration.publish(context,'one','progress',{},'Synthetic progress')
    assert seen['model']['common_goal']==context['payload']['common_goal']
    assert seen['packet']['business_goal']==context['payload']['common_goal']


@pytest.mark.parametrize('role', ['planner', 'executor'])
def test_catalog_declares_structured_groups_and_required_sdk_versions(role):
    from mn_sdk.blueprints import read_blueprint, blueprint_definition, catalog_record
    from mn_sdk.blueprint_source import normalize_blueprint
    package = read_blueprint(ROOT / f'gtm_{role}')
    spec = blueprint_definition(package)
    contract = normalize_blueprint(catalog_record(package, f'gtm_{role}'))['collaboration']
    assert contract['topology'] == 'group' and contract['maxMembers'] == 5
    assert set(contract['accepts']) == {'gtm_planner', 'gtm_executor'}
    fields = {field['path']: field for field in spec['metadata']['init_config_review']['fields']}
    assert fields[contract['peersKey']]['value_type'] == 'array'
    dependencies = json.loads((ROOT / f'gtm_{role}' / 'dependencies.json').read_text())
    versions = {item['name']: item['version'] for item in dependencies['packages']}
    assert versions['mn-python-sdk-collaboration'] == '>=1.3.58.dev0,<2'


@pytest.mark.parametrize('role', ['planner', 'executor'])
def test_group_consumer_scopes_cursors_and_published_members(role, monkeypatch, tmp_path):
    collaboration = load(role, 'collaboration')
    peers = [{'jobId': 'peer-a', 'blueprintId': 'gtm_planner'}, {'jobId': 'peer-b', 'blueprintId': 'gtm_executor'}]
    context = {'payload': {'goal_id': 'bibblio-marketing', 'common_goal': 'Reviewed marketing', 'collaboration_group_id': 'board-a', 'collaboration_peers': peers},
               'stable_job_id': 'self', 'blueprint_id': 'gtm_' + role, 'run_dir': str(tmp_path), 'run_id': 'run', 'started_at': '2026-10-06T00:00:00Z'}
    seen = {}
    def read(**options):
        seen['options'] = options
        return [], {'peer-a': {'execution': 'new-run', 'revision': 2}}, 'connected'
    monkeypatch.setattr(collaboration, 'read_group_work_packets', read)
    old_cursor = {'peer-b': {'execution': 'run-b', 'revision': 7}}
    _, cursor, status = collaboration.peer_updates(context, {'board-a': old_cursor})
    assert seen['options']['cursors'] == old_cursor and status == 'connected'
    assert cursor == {'board-a': {'peer-a': {'execution': 'new-run', 'revision': 2}}}
    context['payload']['collaboration_group_id'] = 'board-b'
    collaboration.peer_updates(context, cursor)
    assert seen['options']['cursors'] == {}
    monkeypatch.setattr(collaboration, 'publish_goal_work_packet', lambda **options: seen.update(packet=options['packet']) or {'status': 'published'})
    collaboration.publish(context, 'one', 'progress', {}, 'Reviewed progress')
    assert seen['packet']['group_id'] == 'board-b'
    assert seen['packet']['group_members'] == ['peer-a', 'peer-b', 'self']
    context['payload']['collaboration_peers'] = peers * 3
    with pytest.raises(ValueError, match='group role'):
        collaboration.peer_updates(context, {})
