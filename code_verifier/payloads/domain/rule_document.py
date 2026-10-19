"""Markdown review projection and explicit supervisor edits; source stays immutable."""
from copy import deepcopy
from hashlib import sha256
import json
import re


def short_title(statement):
    plain = re.sub(r'[`*_#\[\]<>]', '', statement)
    plain = re.sub(r'^(?:the )?(?:software|system|application|app|service)\s+(?:must|shall|should)\s+', '', plain, flags=re.I)
    words = plain.split()
    title = ' '.join(words[:10])
    if len(title) > 80:
        title = title[:77].rsplit(' ', 1)[0] or title[:77]
    title = title[:1].upper() + title[1:]
    return title.rstrip('.,:;') + ('…' if len(words) > 10 or len(plain.strip()) > len(title) + 3 else '')


def document(rules):
    instructions = ['Read or edit each rule in Markdown. Approve all accepts the entire saved list '
                    'before verification starts. Saving an edit never approves the rules.']
    if not rules['rules']:
        instructions.append('## No rules identified\n\nApproval publishes a report with no conformance result.')
    for gap in rules.get('extraction_gaps', []):
        instructions.append(f"## Unresolved document section\n\n{gap['path']}:{gap['start_line']}–{gap['end_line']} "
                            f"({gap['reason']}). Approval accepts this coverage gap; no conformance claim "
                            'covers the missing requirements.')
    limit = rules.get('verification_rule_limit', len(rules['rules']))
    if len(rules['rules']) > limit:
        instructions.append(f'## Verification budget\n\nOnly the first {limit} rules are eligible for '
                            'model investigation. Additional rules remain in the report as Unknown.')
    items = []
    for rule in rules['rules']:
        source = rule['source']
        context = f"Source: `{source['path']}:{source['start_line']}–{source['end_line']}`."
        if rule.get('review_edit'):
            context += ' Edited by the supervisor; the source reference records the original rule origin.'
        items.append({'id': rule['id'], 'title': rule.get('title') or short_title(rule['statement']),
                      'markdown': rule['statement'], 'context': context})
    result = {'schema': 'mn.markdown-review.v1', 'title': 'Review software rules',
              'instructions': '\n\n'.join(instructions), 'items': items}
    notices = []
    if rules.get('extraction_gaps'):
        notices.append(f"{len(rules['extraction_gaps'])} unresolved document sections. Approval accepts these coverage gaps.")
    if len(rules['rules']) > limit:
        notices.append(f'Investigation is limited to {limit} rules; remaining rules will be Unknown.')
    if not rules['rules']:
        notices.append('No rules identified. Approval establishes no conformance result.')
    if notices:
        result['notice'] = ' '.join(notices)
    return result


def encoded_document(rules):
    return json.dumps(document(rules), ensure_ascii=False, sort_keys=True, indent=2) + '\n'


def reference(rules):
    encoded = encoded_document(rules)
    digest = sha256(encoded.encode()).hexdigest()
    if len(encoded.encode()) > 16 * 1024 * 1024:
        raise ValueError('The Markdown review exceeds its 16 MB limit.')
    return {'schema': 'mn.markdown-review.v1', 'artifact_path': f'reviews/rules-{digest}.json',
            'sha256': digest, 'item_count': len(rules['rules'])}


def apply_edit(rules, notes, request):
    edit = json.loads(notes)
    if (not isinstance(edit, dict) or set(edit) != {'id', 'title', 'markdown'}
            or not isinstance(edit['title'], str) or not edit['title'].strip()
            or len(edit['title'].encode('utf-16-le')) // 2 > 120
            or '\n' in edit['title'] or '\r' in edit['title']
            or not isinstance(edit['markdown'], str) or not edit['markdown'].strip()
            or len(edit['markdown'].encode()) > 4000):
        raise ValueError('A rule edit needs its existing ID, a short title and up to 4 KB of Markdown.')
    result = deepcopy(rules)
    match = next((rule for rule in result['rules'] if rule['id'] == edit['id']), None)
    if match is None:
        raise ValueError('The edited rule does not belong to this review.')
    if (match['statement'] == edit['markdown']
            and (match.get('title') or short_title(match['statement'])) == edit['title']):
        raise ValueError('The rule has not changed.')
    match.update(statement=edit['markdown'], title=edit['title'], origin='supervisor',
                 review_edit={'request_id': request['request_id'], 'previous_rules_digest': request['rules_digest']})
    return result
