"""Exact source admission and structured, scoped static judgments."""
from hashlib import sha256
import json
import math

from .source_policy import evidence_paths, source_role

NEXT_STEPS = {
    'budget_exhausted': 'Narrow this rule or increase its investigation budget.',
    'model_unavailable': 'Check the configured model route, then start a fresh review.',
    'invalid_response': 'Review the investigation diagnostics and retry this rule.',
    'parser_gap': 'Inspect the unparsed source and unresolved bindings manually.',
    'capture_gap': 'Include the missing source in a new capture.',
    'ambiguous_rule': 'Clarify the subject, conditions and scope, then approve the revised rule.',
    'insufficient_evidence': 'Inspect the relevant implementation and its calling paths.',
    'runtime_evidence_required': 'Obtain separately authorized runtime measurements or test evidence.',
    'reviewer_disagreement': 'Review the cited implementation and the two assessments.',
}


def evidence_handle(span):
    return 'SRC-' + sha256(json.dumps([span['path'], span['sha256'], span['start_line'],
                                      span['end_line']]).encode()).hexdigest()[:20]


def bind_evidence(result, seen):
    selected = result.get('evidence_ids')
    handles = {evidence_handle(span): span for span in seen}
    if (not isinstance(selected, list) or len(selected) > 12
            or any(not isinstance(value, str) or value not in handles for value in selected)):
        raise ValueError('invalid_evidence: select exact evidence_ids from this investigation')
    if sum(len(handles[value]['text'].encode()) for value in selected) > 48_000:
        raise ValueError('evidence_capacity: select fewer complete source spans within 48 KB')
    return {**result, 'evidence': [{**handles[value], 'quote': handles[value]['text']} for value in dict.fromkeys(selected)]}


def unknown(rule, explanation, history=None, *, reason='insufficient_evidence', seen=()):
    evidence = [{**span, 'quote': span['text'], 'kind': source_role(span['path'])} for span in seen[:4]]
    return {'rule_id': rule['id'], 'status': 'unknown', 'confidence': 0.0,
            'explanation': explanation, 'evidence': evidence, 'investigation': history or [],
            'reason_code': reason, 'next_step': NEXT_STEPS[reason],
            'basis': 'static_review', 'tests_executed': False}


def admit(result, rule, index, seen):
    score, explanation, assessment = result.get('confidence'), result.get('explanation'), result.get('assessment')
    if (type(score) not in {float, int} or not math.isfinite(score) or not 0 <= score <= 1
            or not isinstance(explanation, str) or not explanation.strip() or len(explanation) > 6000
            or not isinstance(assessment, dict)):
        raise ValueError('invalid_assessment: provide finite confidence and a structured assessment')
    support = assessment.get('support')
    if (support not in {'supported', 'contradicted', 'unresolved'}
            or type(assessment.get('scope_matches')) is not bool
            or type(assessment.get('conditions_checked')) is not bool
            or assessment.get('requirement_kind') not in {'behavior', 'configuration', 'source_structure'}
            or assessment.get('reason_code') not in NEXT_STEPS
            or not isinstance(assessment.get('missing_evidence'), str)
            or len(assessment['missing_evidence']) > 2000):
        raise ValueError('invalid_assessment: specify scope, conditions, support and missing evidence')
    status = {'supported': 'pass', 'contradicted': 'fail', 'unresolved': 'unknown'}[support]
    if result.get('status') != status:
        raise ValueError('inconsistent_verdict: status must agree with structured support or contradiction')
    evidence = result.get('evidence')
    if not isinstance(evidence, list) or len(evidence) > 12:
        raise ValueError('invalid_evidence: use at most 12 inspected source spans')
    admitted = []
    for entry in evidence:
        span = index.read(entry.get('path'), entry.get('start_line'), entry.get('end_line'))
        quote = entry.get('quote')
        if (not isinstance(quote, str) or not quote.strip() or quote not in span['text']
                or not any(span['path'] == s['path'] and span['start_line'] >= s['start_line']
                           and span['end_line'] <= s['end_line'] for s in seen)):
            raise ValueError('invalid_evidence: citation was not read or quote is fabricated')
        admitted.append({**span, 'quote': quote, 'kind': source_role(span['path'])})
    enforcement = assessment.get('enforcement_evidence_ids')
    handles = {evidence_handle(span): span for span in admitted}
    if (not isinstance(enforcement, list) or len(enforcement) > 12
            or any(not isinstance(h, str) or h not in handles for h in enforcement)):
        raise ValueError('invalid_evidence: enforcement IDs must be selected inspected citations')
    kind = rule.get('requirement_kind', assessment['requirement_kind'])
    allowed = set(evidence_paths({**rule, 'requirement_kind': kind}, index.paths))
    qualifying = [handles[h] for h in enforcement if handles[h]['path'] in allowed]
    # Configuration can prove a setting, but never a product behavior by itself.
    sufficient = (score >= .6 and assessment['scope_matches'] and assessment['conditions_checked']
                  and assessment['requirement_kind'] == kind
                  and not assessment['missing_evidence'].strip() and bool(qualifying))
    if status != 'unknown' and not sufficient:
        status = 'unknown'
        explanation += ' Insufficient scoped implementation evidence or confidence for a pass/fail judgment.'
    reason = assessment['reason_code'] if support == 'unresolved' else 'insufficient_evidence'
    return {'rule_id': rule['id'], 'status': status, 'confidence': min(score, .49 if status == 'unknown' else .85),
            'model_confidence': score, 'explanation': explanation, 'evidence': admitted,
            'assessment': assessment, **({'reason_code': reason, 'next_step': NEXT_STEPS[reason]} if status == 'unknown' else {}),
            'basis': 'static_review', 'tests_executed': False}
