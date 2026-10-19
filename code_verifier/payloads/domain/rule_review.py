"""Require Core-authoritative conversation approval of the exact frozen ruleset."""
from hashlib import sha256
import json
from pathlib import Path
import time

from mn_sdk import human_interactions
from mn_sdk.agent_events import activity_operation
from mn_sdk.interactions import InteractionError

from .artifacts import read, save, text
from . import rule_document
from .configuration import settings
from .extraction_outcome import require_rule_candidates


class RulesReviewRequired(RuntimeError):
    """Verification cannot proceed without an explicit, matching human decision."""


def review_requests(rules, revision=1):
    digest = sha256(json.dumps(rules, sort_keys=True, ensure_ascii=False,
                               allow_nan=False).encode()).hexdigest()
    return digest, [{'request_id': f'code-rules-{digest}-{revision}',
                     'rules_digest': digest, 'snapshot_id': rules['snapshot_id'],
                     'review_revision': revision, 'decision_type': 'markdown_review',
                     'interaction_kind': 'approval', 'blocking': True,
                     'prompt': 'Review the software rules before verification starts.',
                     'summary': f"Review {len(rules['rules'])} rules before verification",
                     'markdown_review': rule_document.reference(rules),
                     'options': [{'id': 'approve', 'label': 'Approve all', 'action': 'approve'},
                                 {'id': 'revise', 'label': 'Save rule', 'action': 'revise'},
                                 {'id': 'reject', 'label': 'Reject', 'action': 'reject'}]}]


def _status(events, request):
    matching = [event for event in events if isinstance(event, dict)
                and isinstance(event.get('payload'), dict)
                and event['payload'].get('request_id') == request['request_id']]
    published = next((event for event in matching if event.get('type') == 'human_input_requested'), None)
    if published is None:
        return 'missing'
    payload = published['payload']
    if any(payload.get(key) != request[key] for key in ('rules_digest', 'snapshot_id', 'markdown_review', 'review_revision', 'blocking')):
        raise RulesReviewRequired('The human review does not match these rules and source.')
    for event in reversed(matching):
        if event.get('type') == 'human_input_timeout':
            return 'expired'
        if event.get('type') in {'human_input_received', 'human_decision_applied'}:
            answer = event['payload']
            if answer.get('decision') == 'revise':
                return 'revised'
            return 'approved' if answer.get('decision') == 'approve' and answer.get('approved') is True else 'rejected'
    return 'pending'


def _latest_request(events):
    requests = [event['payload'] for event in events if event.get('type') == 'human_input_requested'
                and isinstance(event.get('payload'), dict)
                and event['payload'].get('decision_type') == 'markdown_review']
    return max(requests, key=lambda request: request['review_revision'], default=None)


def require_approved_rules(context, rules):
    """Only the latest Core decision for this exact content grants approval."""
    require_rule_candidates(rules)
    events = human_interactions.read_interaction_events(context['run_id'])
    latest = _latest_request(events)
    digest, requests = review_requests(rules, latest['review_revision'] if latest else 1)
    request = requests[0]
    if not latest or latest['request_id'] != request['request_id'] or _status(events, request) != 'approved':
        raise RulesReviewRequired('Review and approve the saved rules in Chat before verification can start.')
    return {'status': 'approved', 'rules_digest': digest, 'snapshot_id': rules['snapshot_id'],
            'request_ids': [request['request_id']]}


@activity_operation('Waiting for your review of the rules', completed='Rules approved for verification')
def review(context):
    from .rules import markdown
    policy = settings(context)
    rules = read(context, 'rules.json')
    require_rule_candidates(rules)
    if rules['snapshot_id'] != read(context, 'capture.json')['snapshot_id']:
        raise RulesReviewRequired('The rules and source capture do not match.')
    path = Path(context['run_dir']) / 'rules-review-request.json'
    plan = read(context, path.name) if path.is_file() else {
        'snapshot_id': rules['snapshot_id'], 'next_revision': 1,
        'expires_at': int(time.time() * 1000) + policy['human_review_timeout_seconds'] * 1000}
    if plan['snapshot_id'] != rules['snapshot_id']:
        raise RulesReviewRequired('The review belongs to a different source capture.')
    if not path.is_file():
        save(context, 'reviews/original-rules.json', rules)
    refs = [save(context, path.name, plan)]
    while True:
        events = human_interactions.read_interaction_events(context['run_id'])
        latest = _latest_request(events)
        revision = max(plan['next_revision'], latest['review_revision'] if latest else 1)
        digest, requests = review_requests(rules, revision)
        request = requests[0]
        if latest and latest['request_id'] != request['request_id'] and revision == latest['review_revision']:
            # A process can stop between saving an accepted edit and advancing
            # its coordination plan. Reconstruct only that Core-authorized edit.
            if _status(events, latest) == 'revised':
                previous = read(context, f"reviews/state-{latest['rules_digest']}.json")
                if review_requests(previous, revision)[0] != latest['rules_digest']:
                    raise RulesReviewRequired('The saved review state does not match Core.')
                response = next(event['payload'] for event in reversed(events)
                                if event.get('type') == 'human_input_received'
                                and event.get('payload', {}).get('request_id') == latest['request_id'])
                if rule_document.apply_edit(previous, response.get('notes', ''), latest) == rules:
                    plan['next_revision'] = revision + 1
                    save(context, path.name, plan)
                    text(context, 'rules.md', markdown(rules['rules']))
                    continue
            raise RulesReviewRequired('Rules changed after review started outside an authorized rule edit.')
        status = _status(events, request)
        if status in {'rejected', 'expired'}:
            save(context, 'rules-review.json', {'status': status, 'rules_digest': digest})
            raise RulesReviewRequired('Rules were not approved or the review expired. Start a new run to review them.')
        if status == 'approved':
            receipt = require_approved_rules(context, rules)
            refs.append(save(context, 'rules-review.json', receipt))
            return receipt, refs
        remaining = (plan['expires_at'] - int(time.time() * 1000)) / 1000
        if remaining <= 0:
            raise RulesReviewRequired('Rule review expired. Start a new run to review the rules.')
        if status == 'missing':
            save(context, f'reviews/state-{digest}.json', rules)
            refs = [refs[0], text(context, request['markdown_review']['artifact_path'], rule_document.encoded_document(rules))]
            human_interactions.publish_human_interaction_event(
                context['run_id'], 'human_input_requested', {**request, 'expires_at': plan['expires_at']})
        if status != 'revised':
            try:
                human_interactions.await_human_decision(context['run_id'], request['request_id'], timeout=remaining)
            except InteractionError as error:
                if error.code == 'wait_timeout':
                    save(context, 'rules-review.json', {'status': 'wait_expired', 'rules_digest': digest})
                    try:
                        human_interactions.publish_human_interaction_event(
                            context['run_id'], 'human_input_timeout', {'request_id': request['request_id']})
                    except InteractionError:
                        pass
                    raise RulesReviewRequired('Rule review timed out. Start a new run to review the rules.') from error
                raise
            events = human_interactions.read_interaction_events(context['run_id'])
            status = _status(events, request)
        if status == 'revised':
            response = next(event['payload'] for event in reversed(events)
                            if event.get('type') == 'human_input_received'
                            and event.get('payload', {}).get('request_id') == request['request_id'])
            try:
                updated = rule_document.apply_edit(rules, response.get('notes', ''), request)
            except (ValueError, TypeError):
                # Invalid edits never grant approval or destroy the current rules.
                save(context, f'reviews/invalid-edit-{revision}.json', {'request_id': request['request_id'], 'status': 'invalid'})
            else:
                save(context, f'reviews/edit-{revision}.json', {'request_id': request['request_id'],
                     'previous_rules_digest': digest, 'edit': json.loads(response['notes'])})
                save(context, 'rules.json', updated)
                text(context, 'rules.md', markdown(updated['rules']))
                rules = updated
            plan['next_revision'] = revision + 1
            save(context, path.name, plan)
        elif status != 'approved':
            save(context, 'rules-review.json', {'status': status, 'rules_digest': digest})
            raise RulesReviewRequired('Rules were not approved. Review them in Chat before verification.')
