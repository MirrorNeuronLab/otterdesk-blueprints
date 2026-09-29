"""Bounded inbox ingestion; sender content cannot invoke actions or approve work."""
from email.utils import parseaddr
from .contacts import EMAIL
from .model import generate


def poll(state, context, client, *, model=generate):
    cursor = state.get('meta','inbox_cursor',{})
    page = client.list_messages(page_token=cursor.get('page_token'),limit=50)
    messages = page.get('messages')
    if not isinstance(messages,list):
        raise ValueError('Invalid inbox page')
    for summary in messages:
        message_id = summary.get('message_id')
        if not isinstance(message_id,str) or not message_id:
            raise ValueError('Message identity missing')
        labels = set(summary.get('labels') or [])
        if labels & {'bounced','complained','failed'}:
            for recipient in summary.get('to',[]):
                email = parseaddr(recipient)[1].casefold()
                if EMAIL.fullmatch(email):
                    state.suppress(email,'provider_delivery_failure')
            state.put('inbound',message_id,{'status':'suppressed'})
            continue
        if state.get('inbound',message_id):
            continue
        if 'received' not in labels:
            continue
        message = client.get_message(message_id)
        sender = parseaddr(message.get('from') or message.get('from_') or '')[1].casefold()
        if not EMAIL.fullmatch(sender):
            state.put('inbound',message_id,{'status':'quarantined'})
            continue
        subject = str(message.get('subject') or '')[:200]
        body = str(message.get('extracted_text') or message.get('text') or '')[:12000]
        # Honor unambiguous opt-outs without a model call. Classify the remaining
        # mail to prepare a draft or conservatively suppress; never send here.
        if any(phrase in (subject+'\n'+body).casefold() for phrase in ['unsubscribe','remove me','stop emailing','do not contact']):
            intent = 'opt_out'
        else:
            intent = model(context,'classify',{'subject':subject,'body':body}).get('intent')
        if intent not in {'opt_out','complaint','reply','ignore'}:
            raise ValueError('Message classification failed')
        if intent in {'opt_out','complaint'}:
            state.suppress(sender,intent)
        state.put('inbound',message_id,{'status':'new' if intent=='reply' else intent,
            'sender':sender,'subject':subject,'text':body if intent=='reply' else ''})
    next_token = page.get('next_page_token')
    if next_token and next_token == cursor.get('page_token'):
        raise ValueError('Inbox pagination did not advance')
    state.put('meta','inbox_cursor',{'page_token':next_token})
    return not bool(next_token)
