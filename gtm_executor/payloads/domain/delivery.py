"""Exact reviewed drafts and durable per-recipient send claims."""
from email.utils import parseaddr
from .state import digest
from mn_email_receive_agentmail_skill.drafts import AgentMailError


def deliver(state, campaign, client, stop_event, *, approval_status):
    if approval_status != 'approved':
        return {'sent':0,'pending':len(campaign['recipients'])}
    counts = {'sent':0,'suppressed':0,'needs_review':0}
    attempts = [state.attempt(digest({'campaign':campaign['id'],'recipient':email})) for email in campaign['recipients']]
    if any(item and item['status'] != 'sent' for item in attempts):
        return {'sent':sum(bool(item and item['status']=='sent') for item in attempts),
                'suppressed':sum(state.suppressed(email) for email in campaign['recipients']),
                'needs_review':sum(bool(item and item['status']!='sent') for item in attempts)}
    for email in campaign['recipients']:
        if stop_event.is_set():
            break
        if state.suppressed(email):
            counts['suppressed'] += 1
            continue
        key = digest({'campaign':campaign['id'],'recipient':email})
        previous = state.attempt(key)
        if previous:
            counts['sent' if previous['status']=='sent' else 'needs_review'] += 1
            continue
        draft = state.get('draft',key)
        if not draft:
            draft = client.create_draft(client_id=key,to=[email],**campaign['content'],in_reply_to=campaign.get('in_reply_to'))
            if not isinstance(draft.get('draft_id'),str) or not draft['draft_id']:
                raise ValueError('AgentMail did not identify the draft')
            state.put('draft',key,{'draft_id':draft['draft_id']})
        remote = client.get_draft(draft['draft_id'])
        recipients = [parseaddr(value)[1].casefold() for value in remote.get('to',[])]
        if (recipients != [email] or remote.get('cc') or remote.get('bcc') or remote.get('send_at')
            or any(remote.get(k) != v for k,v in campaign['content'].items())
            or remote.get('in_reply_to') != campaign.get('in_reply_to')):
            state.put('delivery_review',key,{'reason':'draft_changed'})
            counts['needs_review'] += 1
            continue
        # A stop or opt-out received before claiming prevents delivery.
        if stop_event.is_set() or state.suppressed(email):
            continue
        if not state.claim(key,{'draft_id':draft['draft_id']}):
            continue
        try:
            result = client.send_draft(draft['draft_id'])
            if not result.get('message_id'):
                raise ValueError('Missing send receipt')
            state.receipt(key,'sent',{'message_id':result['message_id'],'thread_id':result.get('thread_id'),'draft_id':draft['draft_id']})
            counts['sent'] += 1
        except Exception:
            # Even transport failures may have committed remotely. Never retry blindly.
            state.receipt(key,'needs_review',{'draft_id':draft['draft_id'],'reason':'send_outcome_unconfirmed'})
            counts['needs_review'] += 1
            break
        stop_event.wait(1)
    return counts
