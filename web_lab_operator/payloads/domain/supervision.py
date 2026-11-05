"""Volume-based risk notices and confirmed outcomes for the lab supervisor."""

import math

from mn_sdk.blueprint.approvals import publish_human_interaction_event
from mn_sdk.blueprint.hooks import fingerprint

from .protocol import TIP_CAPACITY, WELL_CAPACITY, candidates


def risks_for(step, state):
    """Describe the next step's tracked preconditions, never physical accidents."""
    risks = []

    def add(code, title, message):
        risks.append({'code': code, 'title': title, 'message': message})

    if step['kind'] == 'transfer':
        amount = step['volume_ul']
        source = state['wells'][step['source']]['volume_ul']
        if source + 1e-6 < amount:
            reserves = candidates(step, state)
            recovery = (f"Declared reserve {reserves[0]} has "
                        f"{state['wells'][reserves[0]]['volume_ul']:g} uL. I’ll check the reserve before continuing."
                        if reserves else 'No declared source can supply the full transfer. Review the procedure.')
            add('source_shortage', 'Source shortage',
                f"Simulated source {step['source']} has {source:g} uL; the next transfer needs {amount:g} uL. {recovery}")
        destination = state['wells'][step['destination']]['volume_ul']
        if destination + amount > WELL_CAPACITY + 1e-6:
            add('overflow', 'Overflow risk',
                f"Simulated well {step['destination']} would reach {destination + amount:g} uL, "
                f"above its {WELL_CAPACITY} uL capacity. This transfer cannot proceed. Review the procedure.")
    elif step['kind'] == 'mix':
        available = state['wells'][step['well']]['volume_ul']
        if step['volume_ul'] > min(available, TIP_CAPACITY):
            add('mix_volume', 'Mixing risk',
                f"The {step['volume_ul']:g} uL mix at {step['well']} exceeds the tracked liquid "
                f"or {TIP_CAPACITY} uL tip capacity. This mix cannot proceed. Review the procedure.")
    if step['kind'] in {'transfer', 'mix'}:
        required = math.ceil(step['volume_ul'] / TIP_CAPACITY) if step['kind'] == 'transfer' else 1
        if state['tips_remaining'] < required:
            add('tips', 'Not enough tips',
                f"The next simulated step needs {required} fresh tips; {state['tips_remaining']} remain. "
                'This step cannot proceed. Review the procedure.')
    return risks


def observed_message(event):
    if event['error']:
        return event['error']
    action = event['action']
    if action is None:
        return event['decision']['reason']
    if action['kind'] == 'check_volume':
        label = 'Checked' if event['outcome']['passed'] else 'Check failed'
        return f"{label} {action['well']}: {event['outcome']['observed_ul']:g} uL."
    if action['kind'] == 'transfer':
        return f"Transferred {action['volume_ul']:g} uL from {action['source']} to {action['destination']}."
    if action['kind'] == 'mix':
        return f"Mixed {action['well']}: {action['cycles']} cycles of {action['volume_ul']:g} uL."
    return f"Advanced {action['seconds']:g} virtual seconds."


def outcome_notice(event):
    if event['error'] or event['action'] is None or not event['outcome']['passed']:
        return {'code': 'stopped', 'title': 'Needs review',
                'message': 'The simulation stopped. ' + observed_message(event) + ' Review the procedure before another run.'}
    if event['decision']['decision'] == 'adapt':
        action, primary = event['action'], event['step']['source']
        return {'code': 'recovered', 'title': 'Reserve transfer completed',
                'message': f"Simulated transfer completed: {action['volume_ul']:g} uL from "
                f"{action['source']} to {action['destination']}. {primary} remains at "
                f"{event['after']['wells'][primary]['volume_ul']:g} uL. Continuing the procedure."}
    return None


def publish_notice(block, identity, notice):
    """Core owns Chat delivery; its stable request ID also covers interrupted publication."""
    block.check()
    request_id = fingerprint([block.run_id, identity, notice['code']])

    def publish():
        publish_human_interaction_event(block.run_id, 'human_notice', {
            'request_id': request_id, 'title': notice['title'], 'message': notice['message'],
            'blocking': False, 'requires_ack': False,
        })
        return {'request_id': request_id, **notice}

    block.freeze_checkpoint(f'simulation/notices/{request_id}.json', publish)


def event_rows(trace):
    rows = []
    for event in trace:
        for risk in event.get('risks', []):
            rows.append({'step': event['step']['id'], 'decision': 'warning', 'reason': risk['message']})
        passed = event['outcome']['passed'] and not event['error']
        rows.append({'step': event['step']['id'], 'decision': event['decision']['decision'] if passed else 'needs_review',
                     'reason': observed_message(event)})
    return rows
