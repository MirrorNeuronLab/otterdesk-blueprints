"""Closed protocol language for one-channel, simulation-only liquid handling."""

import copy
import math
import re

ADDRESS = re.compile(r"^[a-z][a-z0-9_]{0,31}/[A-H](?:[1-9]|1[0-2])$")
NAME = re.compile(r"^[a-z][a-z0-9_]{0,31}$")
WELL_CAPACITY = 360
TIP_CAPACITY = 300
MAX_STEPS = 80


def number(value, minimum, maximum, label):
    if type(value) not in (int, float) or not math.isfinite(value) or not minimum <= value <= maximum:
        raise ValueError(f"{label} must be finite and in {minimum}..{maximum}.")
    return value


def closed(value, fields):
    if not isinstance(value, dict) or set(value) != set(fields):
        raise ValueError("Unsupported protocol fields.")


def address(value, plates):
    if not isinstance(value, str) or not ADDRESS.fullmatch(value) or value.split('/')[0] not in plates:
        raise ValueError("Use a declared plate and a well from A1 to H12.")
    return value


def validate_plan(plan, markdown=None):
    closed(plan, {'status', 'summary', 'assumptions', 'unresolved', 'plates', 'liquids', 'steps', 'goals'})
    if plan['status'] not in {'ready', 'needs_review'}:
        raise ValueError("Invalid protocol status.")
    for key in ('summary',):
        if not isinstance(plan[key], str) or not 1 <= len(plan[key]) <= 1000:
            raise ValueError("A bounded protocol summary is required.")
    for key in ('assumptions', 'unresolved'):
        if (not isinstance(plan[key], list) or len(plan[key]) > 30
                or any(not isinstance(s, str) or not 1 <= len(s) <= 1000 for s in plan[key])):
            raise ValueError("Protocol qualifications must be bounded text.")
    plates = plan['plates']
    minimum = 1 if plan['status'] == 'ready' else 0
    if (not isinstance(plates, list) or not minimum <= len(plates) <= 4
            or any(not isinstance(s, str) or not NAME.fullmatch(s) for s in plates)
            or len(set(plates)) != len(plates) or 'tips' in plates):
        raise ValueError("Declare one to four uniquely named 96-well plates.")
    if not isinstance(plan['liquids'], list) or len(plan['liquids']) > 384:
        raise ValueError("Initial liquid inventory exceeds the deck.")
    seen = set()
    for liquid in plan['liquids']:
        closed(liquid, {'well', 'volume_ul', 'liquid'})
        address(liquid['well'], plates)
        number(liquid['volume_ul'], 0, WELL_CAPACITY, 'Initial volume')
        if liquid['well'] in seen or not isinstance(liquid['liquid'], str) or not 1 <= len(liquid['liquid']) <= 80:
            raise ValueError("Each initial well needs one bounded liquid identity.")
        seen.add(liquid['well'])
    steps = plan['steps']
    if not isinstance(steps, list) or not minimum <= len(steps) <= MAX_STEPS:
        raise ValueError("A procedure needs 1..80 supported steps.")
    identities, covered, previous_line = set(), set(), 0
    for step in steps:
        common = {'id', 'kind', 'instruction_lines'}
        fields = {
            'transfer': {'source', 'destination', 'volume_ul', 'alternate_sources'},
            'mix': {'well', 'volume_ul', 'cycles'},
            'wait': {'seconds'},
            'check_volume': {'well', 'minimum_ul', 'maximum_ul'},
        }
        if not isinstance(step, dict) or not isinstance(step.get('kind'), str) or step['kind'] not in fields:
            raise ValueError("Only transfer, mix, wait and check_volume steps are supported.")
        closed(step, common | fields[step['kind']])
        if not isinstance(step['id'], str) or not NAME.fullmatch(step['id']) or step['id'] in identities:
            raise ValueError("Protocol step identities must be unique.")
        identities.add(step['id'])
        lines = step['instruction_lines']
        if (not isinstance(lines, list) or not 1 <= len(lines) <= 20
                or any(type(n) is not int or n < 1 or (markdown is not None and n > len(markdown.splitlines())) for n in lines)):
            raise ValueError("Every step needs valid source Markdown line numbers.")
        covered.update(lines)
        if plan['status'] == 'ready' and min(lines) < previous_line:
            raise ValueError("Protocol steps must preserve the numbered instruction order.")
        previous_line = max(lines)
        for field in ('source', 'destination', 'well'):
            if field in step:
                address(step[field], plates)
        if 'volume_ul' in step:
            number(step['volume_ul'], .1, WELL_CAPACITY, 'Step volume')
        if step['kind'] == 'transfer':
            alternatives = step['alternate_sources']
            if (not isinstance(alternatives, list) or len(alternatives) > 8
                    or any(not isinstance(s, str) for s in alternatives) or len(set(alternatives)) != len(alternatives)):
                raise ValueError("Declare at most eight distinct alternate source wells.")
            for candidate in alternatives:
                address(candidate, plates)
            if step['source'] == step['destination'] or step['destination'] in alternatives:
                raise ValueError("A transfer requires different source and destination wells.")
        elif step['kind'] == 'mix':
            if type(step['cycles']) is not int or not 1 <= step['cycles'] <= 10:
                raise ValueError("Mixing needs 1..10 cycles.")
        elif step['kind'] == 'wait':
            number(step['seconds'], 0, 30, 'Simulated wait')
        else:
            number(step['minimum_ul'], 0, WELL_CAPACITY, 'Minimum volume')
            number(step['maximum_ul'], step['minimum_ul'], WELL_CAPACITY, 'Maximum volume')
    if not isinstance(plan['goals'], list) or not minimum <= len(plan['goals']) <= 384:
        raise ValueError("Declare at least one observable final well-volume goal.")
    seen = set()
    for goal in plan['goals']:
        closed(goal, {'well', 'volume_ul', 'tolerance_ul'})
        address(goal['well'], plates)
        number(goal['volume_ul'], 0, WELL_CAPACITY, 'Goal volume')
        number(goal['tolerance_ul'], 0, 5, 'Goal tolerance')
        if goal['well'] in seen:
            raise ValueError("Final well-volume goals must be unique.")
        seen.add(goal['well'])
    if markdown is not None and plan['status'] == 'ready':
        instructions = {i for i, line in enumerate(markdown.splitlines(), 1)
                        if re.match(r'^\s*\d+[.)]\s+\S', line)}
        if not instructions or instructions - covered:
            raise ValueError("Every numbered Markdown instruction must be represented; clarify missing steps.")
    if plan['status'] == 'ready' and (plan['unresolved'] or plan['assumptions']):
        raise ValueError("Unresolved instructions or assumptions require review before simulation.")
    return copy.deepcopy(plan)


def assessment_valid(block, value):
    validate_plan(value)
    return True


def initial_state(plan):
    wells = {f'{plate}/{row}{column}': {'volume_ul': 0.0, 'liquids': []}
             for plate in plan['plates'] for row in 'ABCDEFGH' for column in range(1, 13)}
    for item in plan['liquids']:
        wells[item['well']] = {'volume_ul': float(item['volume_ul']),
                               'liquids': [item['liquid']]}
    return {'wells': wells, 'tips_remaining': 96}


def candidates(step, state):
    """Only predeclared, nonempty wells containing exactly the same liquid qualify."""
    if step['kind'] != 'transfer':
        return []
    original = state['wells'][step['source']]['liquids']
    return [well for well in [step['source'], *step['alternate_sources']]
            if original and (well == step['source'] or len(original) == 1)
            and state['wells'][well]['liquids'] == original
            and state['wells'][well]['volume_ul'] + 1e-6 >= step['volume_ul']]


def action_for(step, state, decision):
    closed(decision, {'step_id', 'decision', 'source', 'reason'})
    if (decision['step_id'] != step['id'] or decision['decision'] not in {'execute', 'adapt', 'pause'}
            or not isinstance(decision['reason'], str) or not 1 <= len(decision['reason']) <= 1000
            or not isinstance(decision['source'], str)):
        raise ValueError("Invalid adaptive decision.")
    if decision['decision'] == 'pause':
        if decision['source']:
            raise ValueError("A paused decision cannot select a source.")
        return None
    action = copy.deepcopy(step)
    if step['kind'] == 'transfer':
        if decision['source'] not in candidates(step, state):
            raise ValueError("The selected source is unavailable, undeclared or contains another liquid.")
        alternate = decision['source'] != step['source']
        if alternate and state['wells'][step['source']]['volume_ul'] + 1e-6 >= step['volume_ul']:
            raise ValueError("Use the primary source when it has enough liquid.")
        if alternate != (decision['decision'] == 'adapt'):
            raise ValueError("An alternate source must be recorded as an adaptation.")
        action['source'] = decision['source']
        destination = state['wells'][action['destination']]
        if destination['volume_ul'] + action['volume_ul'] > WELL_CAPACITY + 1e-6:
            raise ValueError("The destination would overflow. Review the procedure.")
    elif decision['decision'] != 'execute' or decision['source']:
        raise ValueError("Only transfer source selection can be adapted.")
    if step['kind'] == 'mix' and (step['volume_ul'] > TIP_CAPACITY
            or state['wells'][step['well']]['volume_ul'] < step['volume_ul']):
        raise ValueError("The mixing volume exceeds the available liquid or tip capacity.")
    if step['kind'] in {'transfer', 'mix'}:
        tips = math.ceil(step['volume_ul'] / TIP_CAPACITY) if step['kind'] == 'transfer' else 1
        if state['tips_remaining'] < tips:
            raise ValueError("No unused simulated tips remain for this step.")
    return action


def goal_results(plan, state):
    return [{**goal, 'observed_ul': state['wells'][goal['well']]['volume_ul'],
             'met': abs(state['wells'][goal['well']]['volume_ul'] - goal['volume_ul']) <= goal['tolerance_ul'] + 1e-6}
            for goal in plan['goals']]
