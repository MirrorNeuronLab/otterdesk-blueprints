"""Plan, review and publish campaign ideas; no recipient addresses or send authority."""
import hashlib
import json
import time
from pathlib import Path
from mn_sdk.blueprint_support import WorkflowStateStore
from .research import study
from .model import generate
from .approval import approval
from .collaboration import peer_updates, publish


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()


def validate_brief(result, research):
    fields = ['objective','rationale','message','success_criteria']
    if any(not isinstance(result.get(k),str) or not 1<=len(result[k])<=700 for k in fields):
        raise ValueError('Invalid campaign proposal')
    if result.get('audience') not in {'customer','education_partner','investor'} or result.get('kind') not in {'outreach','newsletter'}:
        raise ValueError('Unsupported campaign audience or kind')
    return {**{k:result[k] for k in fields},'audience':result['audience'],'kind':result['kind'],'facts':research['facts']}


def cycle(context, stop_event):
    store = WorkflowStateStore(Path(context['job_data_dir'])/'state'/'marketing')
    state = store.read('planner.json',{})
    packets,cursor,peer_status = peer_updates(context,state.get('peer_cursor',{}))
    for packet in packets:
        stage = packet.get('stage')
        data = packet.get('analysis',{}).get('modeled_or_inferred',{})
        if stage == 'audience_summary':
            state['audience'] = {'segments':{k:int(v) for k,v in data.get('segments',{}).items() if k in {'customer','education_partner','investor'}},'subscription_status':'unknown'}
        elif stage == 'delivery_outcome':
            state.setdefault('outcomes',{})[data['campaign_id']] = data.get('counts',{})
    state['peer_cursor'] = cursor
    now = time.time()
    research = state.get('research',{})
    if now-research.get('checked_at',0) >= max(86400,int(context['config'].get('marketing',{}).get('website_refresh_seconds',86400))):
        state['research'] = study(context)
        store.write('planner.json',state)
    research = state['research']
    # One idea per day or changed explicit instruction; never recreate a rejected idea in a tight loop.
    generation = fingerprint({'day':int(now//86400),'instruction':context['payload'].get('instruction',''),'common_goal':context['payload'].get('common_goal','')})
    if generation not in state.setdefault('proposals',{}):
        result = generate(context,'campaign',{'research':research,'audience':state.get('audience',{}),
            'observed_outcomes':list(state.get('outcomes',{}).values())[-10:],'instruction':context['payload'].get('instruction',''),'common_goal':context['payload'].get('common_goal','')})
        brief = validate_brief(result,research)
        state['proposals'][generation] = {'common_goal':context['payload'].get('common_goal',''),'brief':brief,'expires_at':int((now+48*3600)*1000),'created_at':now}
        store.write('planner.json',state)
    pending = 0
    for identity,proposal in state['proposals'].items():
        if stop_event.is_set():
            break
        if proposal.get('common_goal','') != context['payload'].get('common_goal',''):
            continue
        brief = proposal['brief']
        preview = 'Approve this campaign idea for drafting? This does not authorize sending.\n\n'+json.dumps(brief,ensure_ascii=False,indent=2)
        status = approval(context,'idea-'+identity,preview,expires_at=proposal['expires_at'])
        proposal['status'] = status
        if status == 'approved':
            publish(context,'brief-'+identity,'approved_brief',{'brief':brief},'A human-reviewed campaign idea is ready for drafting. Final email approval remains required.')
        if status == 'pending': pending += 1
    store.write('planner.json',state)
    return {'status':'running','peer':peer_status,'pending_ideas':pending,'website_checked_at':research['checked_at']}
