"""One bounded evidence investigation per rule, with exact citation admission."""
import math
import json
from hashlib import sha256
import time
from pathlib import Path

from mn_code_search_skill import TextSearchIndex
from mn_sdk.agent_events import activity_operation, report_activity
from mn_sdk.llm import LLMError

from .artifacts import read, save
from .intake import role
from .model import ask, client, failure_details
from .configuration import settings
from .rule_review import require_approved_rules


def evidence_handle(span):
    return 'SRC-' + sha256(json.dumps([span['path'], span['sha256'], span['start_line'],
                                       span['end_line']]).encode()).hexdigest()[:20]


def bind_evidence(result, seen):
    selected = result.get('evidence_ids')
    handles = {evidence_handle(span): span for span in seen}
    if (not isinstance(selected, list) or len(selected) > 12
            or any(not isinstance(value, str) or value not in handles for value in selected)):
        raise ValueError('Select only evidence_ids from source reads in this investigation.')
    return {**result, 'evidence': [{**handles[value], 'quote': handles[value]['text']} for value in selected]}


def unknown(rule, explanation, history=None):
    return {'rule_id': rule['id'], 'status': 'unknown', 'confidence': 0.0,
            'explanation': explanation, 'evidence': [], 'investigation': history or [],
            'basis': 'static_review', 'tests_executed': False}


def admit(result, rule, index, seen):
    status, score = result.get('status'), result.get('confidence')
    explanation = result.get('explanation')
    if (status not in {'pass', 'fail', 'unknown'} or type(score) not in {float, int}
            or not math.isfinite(score) or not 0 <= score <= 1
            or not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 6000):
        raise ValueError('Invalid rule judgment or confidence.')
    evidence = result.get('evidence')
    if not isinstance(evidence, list) or len(evidence) > 12:
        raise ValueError('Invalid rule evidence list.')
    admitted = []
    for entry in evidence:
        if not isinstance(entry, dict):
            raise ValueError('Evidence entries must be objects.')
        span = index.read(entry.get('path'), entry.get('start_line'), entry.get('end_line'))
        quote = entry.get('quote')
        if (not isinstance(quote, str) or not quote.strip() or quote not in span['text']
                or not any(span['path'] == s['path'] and span['start_line'] >= s['start_line']
                           and span['end_line'] <= s['end_line'] for s in seen)):
            raise ValueError('Citation was not read for this rule or its quote is fabricated.')
        admitted.append({**span, 'quote': quote, 'kind': role(span['path'])})
    # A test definition or specification is not an observed implementation.
    if status != 'unknown' and (score < .6 or not any(e['kind'] == 'implementation' for e in admitted)):
        status = 'unknown'
        explanation += ' Insufficient implementation evidence or confidence for a pass/fail judgment.'
    return {'rule_id': rule['id'], 'status': status, 'confidence': min(score, .49 if status == 'unknown' else .85),
            'model_confidence': score, 'explanation': explanation, 'evidence': admitted,
            'basis': 'static_review', 'tests_executed': False}


def verify_rule(context, rule, index, analysis, llm, *, files=None, deadline=float('inf')):
    policy = settings(context)
    transcript, seen, history = [], [], []
    model_errors = 0
    inventory = files if files is not None else [{'path': p, 'kind': role(p)} for p in read(context, 'capture.json')['sources']]
    visible, size = [], 0
    for item in sorted(inventory, key=lambda item: item['kind'] != 'implementation'):
        length = len(json.dumps(item, ensure_ascii=False).encode())
        if len(visible) >= 512 or size + length > 24_000:
            break
        visible.append(item)
        size += length
    packet = {'rule': rule, 'snapshot_id': index.snapshot_id,
              'files': visible, 'file_inventory': {'total': len(inventory), 'shown': len(visible),
                  'truncated': len(visible) < len(inventory), 'search_covers_all_captured_files': True},
              'syntax_coverage': analysis['coverage'], 'limitations': analysis['limitations']}
    for _ in range(policy['max_turns_per_rule']):
        if time.monotonic() >= deadline:
            break
        try:
            result = ask(llm, 'verify.md', {**packet, 'observations': transcript})
            action = result.get('action')
            if action == 'finish':
                return {**admit(bind_evidence(result, seen), rule, index, seen), 'investigation': history}
            if action == 'search':
                observation = index.search(result.get('query'), limit=12)
            elif action == 'read':
                observation = index.read(result.get('path'), result.get('start_line'), result.get('end_line'))
                observation['evidence_id'] = evidence_handle(observation)
                seen.append(observation)
            else:
                raise ValueError('Use only search, read, or finish.')
            entry = {'request': result, 'result': observation}
            transcript.append(entry)
            history.append(entry)
            model_errors = 0
        except (ValueError, TypeError, KeyError, LLMError, TimeoutError) as error:
            model_errors = model_errors + 1 if isinstance(error, (LLMError, TimeoutError)) else 0
            entry = {'error': type(error).__name__, 'recovery':
                'Choose a valid search/read action or a different query. Finish only with evidence_ids '
                'from inspected source reads and a valid confidence. Use unknown when evidence is insufficient.'}
            if isinstance(error, (LLMError, TimeoutError)):
                entry['diagnostic'] = failure_details(error)
            transcript.append(entry)
            history.append(entry)
            if model_errors >= 3:
                return {**unknown(rule, 'Model requests remained unavailable after bounded retries.', history),
                        'reason_code': 'model_unavailable', 'diagnostic': failure_details(error)}
        # Preserve the full audit history; bound the next request's working context.
        while transcript and len(json.dumps(transcript, ensure_ascii=False).encode()) > 24_000:
            transcript.pop(0)
    return unknown(rule, 'Investigation reached its turn or time limit without an admissible judgment.', history)


@activity_operation('Verifying rules one by one', completed='Rule verification saved')
def verify(context, llm=None):
    policy = settings(context)
    deadline = time.monotonic() + policy['verification_timeout_seconds']
    capture, rules = read(context, 'capture.json'), read(context, 'rules.json')
    index, analysis = TextSearchIndex(capture['sources']), read(context, 'static-analysis.json')
    if rules['snapshot_id'] != index.snapshot_id:
        raise ValueError('Rules and captured source do not match.')
    approval = require_approved_rules(context, rules)
    results, refs = [], []
    files = [{'path': p, 'kind': role(p)} for p in capture['sources']]
    for number, rule in enumerate(rules['rules'], 1):
        name = f"verification/{rule['id']}.json"
        reuse = (Path(context['run_dir']) / name).is_file()
        if reuse:
            value = read(context, name)
            if value['snapshot_id'] != index.snapshot_id or value['rule'] != rule:
                raise ValueError('Saved verification does not match this rule and capture.')
            result = value['result']
            # An outage placeholder without an investigation is unfinished work.
            reuse = not (result.get('reason_code') == 'model_unavailable' and not result.get('investigation'))
        if not reuse:
            report_activity(f"Checking rule {number} of {len(rules['rules'])}", kind='action', run_dir=context['run_dir'])
            if number > policy['max_rules']:
                result = unknown(rule, 'The configured rule investigation limit was reached; this rule was not assessed.')
            else:
                llm = llm or client(context)
                result = verify_rule(context, rule, index, analysis, llm, files=files, deadline=deadline)
            value = {'snapshot_id': index.snapshot_id, 'rule': rule, 'result': result}
        refs.append(save(context, name, value))
        results.append(result)
    refs.append(save(context, 'verification.json', {'snapshot_id': index.snapshot_id, 'results': results,
                                                 'rules_review': approval}))
    return {'verified': len(results), 'unknown': sum(r['status'] == 'unknown' for r in results)}, refs
