"""Bind model-selected source handles to trusted captured text."""
from hashlib import sha256
from copy import deepcopy


class ExtractionContractError(ValueError):
    """A model response needs correction before any rules are admitted."""


class SourceSelectionError(ExtractionContractError):
    def __init__(self, indices):
        super().__init__('Select source_ids copied exactly from numbered_lines.id for the listed rules.')
        self.indices = indices


def source_lines(packet):
    return [{'id': f'L{packet["start_line"] + number}-{sha256(line.encode()).hexdigest()[:12]}',
             'line': packet['start_line'] + number, 'text': line}
            for number, line in enumerate(packet['text'].splitlines(keepends=True))]


def bind_sources(index, packet, response):
    if response.get('complete') is not True or not isinstance(response.get('rules'), list):
        raise ExtractionContractError('Return the complete rules list and complete=true; do not omit rules.')
    handles = {line['id']: line['line'] for line in source_lines(packet)}
    rules, invalid = [], []
    for number, item in enumerate(response['rules']):
        if not isinstance(item, dict):
            raise ExtractionContractError('Every extracted rule must be an object.')
        selected = item.get('source_ids')
        if (not isinstance(selected, list) or not 1 <= len(selected) <= len(handles)
                or any(not isinstance(value, str) or value not in handles for value in selected)):
            invalid.append(number)
            continue
        numbers = [handles[value] for value in selected]
        span = index.read(packet['path'], min(numbers), max(numbers))
        rules.append({'statement': item.get('statement'), 'start_line': span['start_line'],
                      'end_line': span['end_line'], 'quote': span['text']})
    if invalid:
        raise SourceSelectionError(invalid)
    return {'complete': True, 'rules': rules}


def apply_source_repairs(original, indices, response):
    repairs = response.get('repairs')
    if not isinstance(repairs, list) or len(repairs) != len(indices):
        raise ExtractionContractError('Return exactly one repair for each listed index; preserve all rules.')
    seen, result = set(), deepcopy(original)
    for item in repairs:
        number = item.get('index') if isinstance(item, dict) else None
        if type(number) is not int or number not in indices or number in seen:
            raise ExtractionContractError('Repair indices must match the listed rules exactly once.')
        seen.add(number)
        result['rules'][number]['source_ids'] = item.get('source_ids')
    return result
