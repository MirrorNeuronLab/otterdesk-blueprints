"""Public product facts stay source-backed and separate from contact data."""
import time
from urllib.parse import urlsplit
from mn_web_browser_skill import WebBrowserConfig, browse
from .model import generate


def study(context, *, browser=browse, model=generate):
    url = context['payload']['website_url']
    parts = urlsplit(url)
    if parts.scheme != 'https' or parts.hostname not in {'bibblio.app','www.bibblio.app'} or parts.username or parts.port:
        raise ValueError('The marketing website must be the public Bibblio HTTPS site')
    page = browser(url,depth='standard',config=WebBrowserConfig(allow_hosts=('bibblio.app','www.bibblio.app'),
        timeout_seconds=20,total_timeout_seconds=45,max_attempts=1,max_chars=16000,workflow_id=context['run_id']))
    text = page.get('text','')
    if page.get('status') != 'ok' or len(text.strip())<100:
        raise RuntimeError('Bibblio product evidence is unavailable')
    result = model(context,'research',{'url':url,'website_text':text})
    facts = result.get('facts')
    if not isinstance(facts,list) or not 1<=len(facts)<=10:
        raise ValueError('Research did not return bounded facts')
    verified=[]
    for fact in facts:
        if not isinstance(fact,dict) or not isinstance(fact.get('quote'),str) or not 5<=len(fact['quote'])<=240 or fact['quote'] not in text:
            raise ValueError('Research citation was not present in the website evidence')
        # Use the actual quotation as the claim rather than an unverified model paraphrase.
        verified.append({'claim':fact['quote'],'source_url':url})
    return {'facts':verified,'checked_at':time.time(),'source_url':url}
