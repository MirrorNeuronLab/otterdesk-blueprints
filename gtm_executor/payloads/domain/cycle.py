"""Executor policy: ingest, draft, review, deliver, and publish aggregate outcomes."""
import os
import time
from collections import Counter
from mn_email_receive_agentmail_skill.drafts import AgentMailDraftClient
from .state import State, digest
from .contacts import import_contacts, select_recipients, segment
from .collaboration import peer_updates, publish
from .drafting import compose, campaign_id, review_preview
from .approval import approval
from .delivery import deliver
from .inbox import poll


def prepare_campaign(state, context, brief, *, source_id, recipients=None, incoming=None, model=None):
    if state.get('source',source_id):
        return
    audience = brief.get('audience')
    if brief.get('kind') == 'newsletter' and context['payload'].get('newsletter_eligible') is not True:
        state.put('source',source_id,{'status':'newsletter_consent_required'})
        return
    limit = min(25,max(1,int(context['config'].get('marketing',{}).get('max_campaign_recipients',25))))
    recipients = recipients if recipients is not None else select_recipients(state,audience,limit)
    if not recipients:
        return
    content = compose(context,brief,incoming=incoming,**({'model':model} if model else {}))
    reply_id = incoming.get('message_id') if incoming else None
    identity = campaign_id(brief,recipients,content,context['payload']['inbox_id'],reply_id)
    campaign = {'id':identity,'brief':brief,'recipients':recipients,'content':content,
        'inbox_id':context['payload']['inbox_id'],'in_reply_to':reply_id,
        'created_at':time.time(),'expires_at':int((time.time()+48*3600)*1000)}
    review_preview(campaign) # Validate visible size before persisting a source as consumed.
    if len(review_preview(campaign)) > 7800:
        raise ValueError('Campaign is too large to review in one approval')
    state.put('campaign',identity,campaign)
    state.put('source',source_id,{'campaign_id':identity})


def cycle(context, stop_event):
    state = State(context['job_data_dir'])
    import_contacts(state,context['payload']['contacts_file'])
    client = AgentMailDraftClient(api_key=os.environ.get('AGENTMAIL_API_KEY',''),inbox_id=context['payload']['inbox_id'])
    caught_up = poll(state,context,client)
    counts = dict(Counter(segment(row) for row in state.get('meta','contacts',{}).values()))
    publish(context,'audience-'+digest(counts),'audience_summary',{'segments':counts,'subscription_status':'unknown'},'Audience segments are ready for human review.')
    packets,cursor,peer_status = peer_updates(context,state.get('meta','peer_cursor',{}))
    for packet in packets:
        if stop_event.is_set():
            return {'status':'stopped'}
        if packet.get('stage') != 'approved_brief':
            continue
        brief = packet.get('analysis',{}).get('modeled_or_inferred',{}).get('brief')
        if not isinstance(brief,dict) or len(str(brief))>10000:
            raise ValueError('Invalid campaign handoff')
        prepare_campaign(state,context,brief,source_id=packet['work_packet_id'])
    state.put('meta','peer_cursor',cursor)
    instruction = context['payload'].get('instruction','').strip()
    default_instruction = 'Market Bibblio through relevant, human-approved email outreach.'
    if instruction and instruction != default_instruction:
        prepare_campaign(state,context,{'objective':instruction,'audience':'education_partner','kind':'outreach'},source_id='instruction-'+digest(instruction))
    for mid,message in state.items('inbound'):
        if message.get('status') == 'new' and not state.suppressed(message['sender']):
            prepare_campaign(state,context,{'objective':'Answer the inbound question using only verified Bibblio facts; ask for human help when facts are missing.','audience':'customer','kind':'reply'},source_id='reply-'+mid,
                recipients=[message['sender']],incoming={'message_id':mid,**message})
            state.put('inbound',mid,{**message,'status':'drafted'})
    totals = {'sent':0,'suppressed':0,'needs_review':0,'pending':0}
    for key,campaign in state.items('campaign'):
        if stop_event.is_set():
            break
        # Sender/content/recipients cannot drift after review.
        actual = campaign_id(campaign['brief'],campaign['recipients'],campaign['content'],campaign['inbox_id'],campaign.get('in_reply_to'))
        if actual != key or campaign['inbox_id'] != client.inbox_id:
            raise ValueError('Campaign revision changed')
        status = approval(context,'send-'+key,review_preview(campaign),expires_at=campaign['expires_at'])
        if status == 'approved' and caught_up:
            result = deliver(state,campaign,client,stop_event,approval_status=status)
            for k,v in result.items(): totals[k] += v
            publish(context,'outcome-'+key+'-'+digest(result),'delivery_outcome',{'campaign_id':key,'counts':result},'Observed campaign delivery results; accepted messages are not proof of inbox delivery.')
        elif status == 'pending':
            totals['pending'] += 1
    return {'status':'running','peer':peer_status,'inbox_caught_up':caught_up,'contacts':sum(counts.values()),'quarantined':len(state.get('meta','quarantine',[])),**totals}
