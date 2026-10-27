"""Bounded, source-first investigations with independently checked judgments."""
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import time

from mn_sdk.agent_events import report_activity
from mn_sdk.llm import LLMError
from mn_code_search_skill import SyntaxIndex, TextSearchIndex

from .artifacts import read, save
from .configuration import BLUEPRINT_ID, settings, phase_deadline
from .evidence import admit, bind_evidence, evidence_handle, unknown
from .model import ask, client, failure_details
from .retrieval import EvidenceWorkspace, compact_observations
from .rule_review import require_approved_rules

RECOVERY = {
    'invalid_source_span': 'Use an existing captured path and 1..200 existing complete lines.',
    'read_capacity': 'Read fewer complete lines; the source span exceeded the byte allowance.',
    'invalid_evidence': 'Select only exact evidence IDs from inspected source reads for this rule.',
    'evidence_capacity': 'Select fewer whole source spans within the 48 KB judgment allowance.',
    'inconsistent_verdict': 'Make the status agree with the structured support or contradiction assessment.',
    'repeated_query': 'This search already ran. Change terms, inspect a candidate, or use symbols/trace.',
    'invalid_assessment': 'Provide scope, conditions, support, enforcement evidence and missing evidence.',
    'invalid_symbol': 'Use a discovered qualified symbol and trace depth 1..3.',
}


def policy_identity(analysis):
    root = Path(__file__).parent
    paths = [root / name for name in ('verification.py', 'evidence.py', 'retrieval.py', 'source_policy.py', 'model_contracts.py')]
    paths += [root.parent / 'prompts' / name for name in ('verify.md', 'judge.md', 'critique.md')]
    return {'policy': 'scoped-static-review-v2', 'implementation': sha256(b''.join(p.read_bytes() for p in paths)).hexdigest(),
            'analysis_version': analysis['analysis_version'], 'ranking_version': TextSearchIndex.ranking_version,
            'navigation_version': SyntaxIndex.navigation_version}


def verify_rule(block, rule, index, analysis, llm, *, files=None, deadline=float('inf'), workspace=None):
    policy = settings(block)
    block.check()
    if time.monotonic() >= deadline:
        return unknown(rule, 'The configured verification deadline was reached.', reason='budget_exhausted')
    workspace = workspace or EvidenceWorkspace(index.copy_sources(), analysis)
    candidates, seen = workspace.seed(rule)
    history = [{'request': {'action': 'seed'}, 'result': candidates},
               {'request': {'action': 'seed_reads'}, 'result': list(seen)}]
    packet = {'rule': rule, 'snapshot_id': index.snapshot_id, 'project_map': workspace.map,
              'candidates': candidates, 'syntax_coverage': analysis['coverage'],
              'limitations': analysis['limitations'], 'seed_reads': list(seen)}
    queries, calls, model_errors, draft = set(), 0, 0, None

    def request(prompt, body):
        nonlocal calls
        block.check()
        if time.monotonic() >= deadline:
            raise TimeoutError('Verification computation budget reached.')
        calls += 1
        return ask(llm, prompt, body)

    def complete(result):
        result['diagnostics'] = {'model_calls': calls, 'seeded_reads': len(packet['seed_reads']),
            'source_reads': len(seen),
            'searches': sum(h.get('request', {}).get('action') in {'search', 'rank'} for h in history),
            'empty_searches': sum(h.get('request', {}).get('action') in {'search', 'rank'}
                                  and not h.get('result', {}).get('matches') for h in history),
            'repeated_queries': sum(h.get('error_code') == 'repeated_query' for h in history)}
        return result

    for turn in range(policy['max_turns_per_rule'] - 2):
        observations, catalog = compact_observations(history, seen)
        try:
            result = request('verify.md', {**packet, 'observations': observations,
                'evidence_catalog': catalog, 'investigation_calls_remaining': policy['max_turns_per_rule'] - 3 - turn})
            action = result.get('action')
            if action == 'finish':
                draft = admit(bind_evidence(result, seen), rule, index, seen)
                break
            if action in {'search', 'rank'}:
                query = result.get('query')
                key = (action, query.casefold().strip()) if isinstance(query, str) else None
                if key in queries:
                    raise ValueError('repeated_query: choose different terms or inspect source')
                observation = (workspace.rank(rule, query) if action == 'rank' else index.search(query))
                queries.add(key)
            elif action == 'read':
                observation = workspace.read(result.get('path'), result.get('start_line'), result.get('end_line'))
                if not any(evidence_handle(observation) == evidence_handle(s) for s in seen):
                    seen.append(observation)
            elif action == 'symbols':
                observation = workspace.symbols(result.get('query'))
            elif action == 'trace':
                observation = workspace.trace(result.get('symbol'), result.get('depth'))
            else:
                raise ValueError('invalid_action: use rank, search, symbols, trace, read or finish')
            history.append({'request': result, 'result': observation})
            model_errors = 0
        except (ValueError, TypeError, KeyError, LLMError, TimeoutError) as error:
            unavailable = isinstance(error, (LLMError, TimeoutError))
            code = str(error).partition(':')[0] if isinstance(error, ValueError) else ''
            entry = {'error': type(error).__name__, 'error_code': code if code in RECOVERY else 'invalid_response',
                     'recovery': RECOVERY.get(code, 'Use a valid bounded action or finish Unknown with the missing evidence.')}
            if unavailable:
                entry['diagnostic'] = failure_details(error)
            history.append(entry)
            model_errors = model_errors + 1 if unavailable else 0
            if model_errors >= 3 or time.monotonic() >= deadline:
                reason = 'budget_exhausted' if time.monotonic() >= deadline else 'model_unavailable'
                return complete(unknown(rule, 'Investigation stopped before a judgment was available.', history,
                                        reason=reason, seen=seen))
    try:
        if draft is None:
            observations, catalog = compact_observations(history, seen)
            result = request('judge.md', {**packet, 'observations': observations, 'evidence_catalog': catalog})
            draft = admit(bind_evidence(result, seen), rule, index, seen)
        if draft['status'] != 'unknown':
            # The critic receives the approved rule and exact selected source,
            # never the draft's status, confidence or explanation.
            critique = request('critique.md', {'rule': rule, 'snapshot_id': index.snapshot_id,
                'evidence_reads': [{**span, 'evidence_id': evidence_handle(span)} for span in draft['evidence']],
                'syntax_coverage': analysis['coverage'], 'limitations': analysis['limitations']})
            checked = admit(bind_evidence(critique, draft['evidence']), rule, index, draft['evidence'])
            draft['independent_review'] = {key: checked[key] for key in ('status', 'assessment', 'explanation', 'confidence')}
            if checked['status'] != draft['status']:
                draft.update(status='unknown', confidence=0.0, reason_code='reviewer_disagreement',
                             next_step='Review the cited implementation and the two assessments.')
            else:
                draft['confidence'] = min(draft['confidence'], checked['confidence'])
        if draft['status'] == 'unknown' and not draft['evidence']:
            draft['evidence'] = unknown(rule, draft['explanation'], seen=seen)['evidence']
        return complete({**draft, 'investigation': history})
    except (ValueError, TypeError, KeyError, LLMError, TimeoutError) as error:
        reason = ('budget_exhausted' if time.monotonic() >= deadline else
                  'model_unavailable' if isinstance(error, (LLMError, TimeoutError)) else 'invalid_response')
        history.append({'error': type(error).__name__, 'stage': 'judgment_or_critique'})
        return complete(unknown(rule, 'No admissible, independently checked judgment was available.', history,
                                reason=reason, seen=seen))


def verify(block, inputs, *, llm=None):
    report_activity('Verifying scoped rules', owner_blueprint=BLUEPRINT_ID,
                    step_id=block.step_id, run_dir=block.store.run_dir)
    capture_ref = inputs['previous']['capture']
    capture = block.store.read(capture_ref)
    llm = llm or block.resources.get('llm')
    policy = settings(block)
    deadline = phase_deadline(policy, 'verification_timeout_seconds')
    rules, analysis = read(block, 'rules.json'), read(block, 'static-analysis.json')
    workspace = EvidenceWorkspace(capture['sources'], analysis)
    index = workspace.index
    if rules['snapshot_id'] != index.snapshot_id:
        raise ValueError('Rules and captured source do not match.')
    approval = require_approved_rules(block, rules)
    identity = {**policy_identity(analysis), 'rules_digest': approval['rules_digest']}
    results = []
    for number, rule in enumerate(rules['rules'], 1):
        block.check()
        name = f"verification/{rule['id']}.json"
        reuse = block.store.path(name).is_file()
        if reuse:
            value = read(block, name)
            if value['snapshot_id'] != index.snapshot_id or value['rule'] != rule or value.get('policy') != identity:
                raise ValueError('Saved verification uses different rules, source or analysis policy. Start a fresh run.')
            result = value['result']
            reuse = not (result.get('reason_code') == 'model_unavailable' and not result.get('investigation'))
        if not reuse:
            report_activity(f"Checking rule {number} of {len(rules['rules'])}", kind='action',
                            run_dir=block.store.run_dir, owner_blueprint=BLUEPRINT_ID)
            if number > policy['max_rules'] or time.monotonic() >= deadline:
                result = unknown(rule, 'The configured investigation limit or deadline was reached; this rule was not assessed.',
                                 reason='budget_exhausted')
            else:
                llm = llm or client()
                result = verify_rule(block, rule, index, analysis, llm, deadline=deadline, workspace=workspace)
            value = {'snapshot_id': index.snapshot_id, 'rule': rule, 'result': result, 'policy': identity}
        save(block, name, value)
        results.append(result)
    diagnostics = dict(Counter(r.get('reason_code') for r in results if r['status'] == 'unknown'))
    totals = Counter()
    for result in results:
        totals.update(result.get('diagnostics', {}))
    reference = block.store.commit('verification.json', {'snapshot_id': index.snapshot_id,
        'results': results, 'rules_review': approval, 'verification_policy': identity,
        'diagnostics': {'unknown_reasons': diagnostics, **dict(totals)}},
        kind='rule_verification')
    return {'verified': len(results), 'unknown': sum(r['status'] == 'unknown' for r in results),
            'capture': capture_ref, 'verification': reference.to_dict()}
