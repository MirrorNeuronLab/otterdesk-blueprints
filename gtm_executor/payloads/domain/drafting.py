"""Render reviewed copy into a safe email template without model-generated markup."""
import html
from .model import generate
from .state import digest


def compose(context, brief, *, incoming=None, model=generate):
    data = model(context,'draft',{'brief':brief,'incoming':incoming,'website_url':context['payload']['website_url']})
    subject = data.get('subject')
    paragraphs = data.get('paragraphs')
    if not isinstance(subject,str) or not 1<=len(subject)<=150 or '\r' in subject or '\n' in subject:
        raise ValueError('Invalid email subject')
    if not isinstance(paragraphs,list) or not 1<=len(paragraphs)<=6 or any(not isinstance(p,str) or not p.strip() or len(p)>600 for p in paragraphs):
        raise ValueError('Invalid email body')
    footer = 'Bibblio team\nhttps://bibblio.app\nReply "unsubscribe" if you do not want further marketing emails.'
    text = '\n\n'.join(paragraphs) + '\n\n' + footer
    body = ''.join('<p style="margin:0 0 18px;line-height:1.65">'+html.escape(p)+'</p>' for p in paragraphs)
    markup = '<!doctype html><html><body style="margin:0;background:#f5f3ee;color:#26372f;font-family:Arial,sans-serif"><div style="max-width:560px;margin:24px auto;padding:32px;background:#fff;border-radius:12px"><p style="font-size:22px;font-weight:bold;color:#39654c">Bibblio</p>'+body+'<p><a href="https://bibblio.app" style="color:#39654c">Explore Bibblio</a></p><hr><p style="font-size:12px;color:#68756e">'+html.escape(footer).replace('\n','<br>')+'</p></div></body></html>'
    return {'subject':subject,'text':text,'html':markup}


def campaign_id(brief, recipients, content, inbox_id, in_reply_to=None):
    return digest({'brief':brief,'recipients':recipients,'content':content,'inbox_id':inbox_id,'in_reply_to':in_reply_to})


def review_preview(campaign):
    # HTML is a fixed, escaped rendering of exactly the plain-text paragraphs.
    return ('Approve this exact email'+(' reply' if campaign.get('in_reply_to') else ' campaign')+'?\n\n'
        +'From: '+campaign['inbox_id']+'\nRecipients:\n'+'\n'.join(campaign['recipients'])
        +'\n\nSubject: '+campaign['content']['subject']+'\n\n'+campaign['content']['text']
        +'\n\nHTML uses the Bibblio template with the same copy and website link. Approval expires in 48 hours.\n'
        +'Contact categories are unverified; verify recipient relevance before approving.')
