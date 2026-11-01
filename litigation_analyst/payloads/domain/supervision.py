"""Prioritize a source-bound human handoff without granting approval or starting work."""
import html


BOUNDARY = 'Discussing this question does not approve findings, start another run or authorize sharing. Record wording decisions in the finding review.'


def compact(value, maximum):
    text = ' '.join(str(value or '').split())
    return text if len(text) <= maximum else text[:maximum - 1].rstrip() + '…'


def build(workspace):
    """Only project the cleared workspace; never inspect hidden sources or infer consent."""
    evidence = {p['evidence_id'] for p in workspace['evidence']}
    findings = workspace['findings']
    review = workspace.get('reading_review', workspace.get('consistency', {}))
    checks = [c for c in review.get('checks', []) if set(c.get('evidence_ids', [])) <= evidence]
    blocked = set(review.get('withheld_finding_ids', [])) | {c['finding_id'] for c in checks}
    retained = [f for f in findings if f['id'] not in blocked and f.get('model_finding_id') not in blocked
                and f.get('review_state') != 'Dismissed'
                and set(f.get('supporting_evidence', []) + f.get('counter_evidence', [])) <= evidence]

    def question(kind, text, reason, timing, ids=(), **target):
        if not set(ids) <= evidence:
            raise ValueError('Human review question has unavailable evidence')
        return {'kind': kind, 'question': text, 'reason': reason, 'timing': timing,
                'evidence_ids': list(dict.fromkeys(ids)), **target}

    # Handling precedes substantive use. Conflicting/changed bases precede ordinary drafts.
    handling = next((g for g in workspace['gaps'] if g.get('work_type') == 'handling_review'), None)
    if handling:
        next_review = question('handling', 'Which handling restriction should counsel resolve before further review?',
            'A proposed follow-up requires a handling decision. Restricted material remains excluded; a Chat answer cannot clear it.',
            'Before any substantive use of restricted material', handling['source_evidence_ids'], gap_id=handling['id'])
    elif checks:
        next_review = question('consistency', 'Which draft wording needs correction after you compare the conflicting records?',
            'An available source record conflicts with a draft claim. The claim is withheld; review the complete record before relying on it.',
            'Before relying on or sharing the draft', checks[0].get('evidence_ids', []))
    else:
        changed = next((f for f in retained if f.get('review_state') in {'Needs reassessment', 'Reviewers disagree'}), None)
        pending_states = {'AI draft', 'Request evidence'}
        pending = next((f for f in retained if f.get('review_state', 'AI draft') in pending_states and f.get('counter_evidence')), None)
        pending = changed or pending or next((f for f in retained if f.get('review_state', 'AI draft') in pending_states), None)
        if pending:
            state = pending.get('review_state', 'AI draft')
            reason = {'Needs reassessment': 'The source basis changed. The earlier review does not approve this version.',
                      'Reviewers disagree': 'Reviewers disagree. Their decisions have not become an approved consensus.',
                      'Request evidence': 'Further evidence was requested. The finding remains unresolved until its source basis is reviewed.'}.get(state,
                      'This is an AI draft. Compare its support, contrary records and limitations before choosing wording.')
            next_review = question('finding', 'How should “' + compact(pending['title'], 150) + '” be qualified before use?',
                reason, 'Before relying on this finding', pending.get('supporting_evidence', []) + pending.get('counter_evidence', []),
                finding_id=pending['id'])
        else:
            gaps = sorted(workspace['gaps'], key=lambda g: 0 if g.get('priority') == 'High' else 1)
            if gaps:
                gap = gaps[0]
                internal = gap.get('work_type') == 'internal_reread'
                next_review = question('gap', gap['question'],
                    ('Matching records are already available. Re-read them before requesting additional evidence. ' if internal else '') + gap['why_it_matters'],
                    'Before planning further evidence work', gap['source_evidence_ids'], gap_id=gap['id'])
            else:
                unexamined = next((q for q in workspace.get('counsel_issues', []) if not q.get('hypothesis_ids')), None)
                next_review = question('scope', 'Should the next review focus on “' + compact(unexamined['question'], 150) + '”?' if unexamined
                    else 'Which source-backed question should the next review focus on?',
                    'This counsel question was not examined in this review.' if unexamined else
                    'Choose the next question after inspecting the saved draft and its coverage. No additional investigation has started.',
                    'When planning another review')
    return {'next_review': next_review, 'retained_finding_ids': [f['id'] for f in retained],
            'boundary': BOUNDARY}


def chat_summary(workspace):
    handoff = build(workspace)
    ids = set(handoff['retained_finding_ids'])
    highlights = []
    for finding in workspace['findings']:
        if finding['id'] not in ids:
            continue
        # Never shorten a substantive claim in a way that could lose its qualification.
        basis = f"Support: {len(finding.get('supporting_evidence', []))} passage(s); contrary: {len(finding.get('counter_evidence', []))}."
        reviewed = finding.get('review_state') in {'Reviewed with qualification', 'Revised'} and finding.get('reviewed_text')
        excerpt = 'Reviewed wording excerpt: ' + finding['reviewed_text'] if reviewed else 'Draft excerpt: ' + finding['assessment']
        if len(excerpt) + len(basis) + 1 > 320:
            excerpt = 'Read the full finding to inspect its complete assessment, contrary records and qualifications.'
        highlights.append({'title': compact(finding['title'], 180),
            'detail': excerpt + ' ' + basis})
        if len(highlights) == 3:
            break
    coverage = workspace.get('coverage', {})
    readable = len(coverage.get('readable_ids', []))
    total = len(coverage.get('source_ids', workspace['sources']))
    sample = 'Synthetic sample. ' if workspace.get('sample') else ''
    next_review = handoff['next_review']
    return {'schema_version': 'otterdesk.report-summary.v1', 'status': 'Draft for legal review',
        'overview': f"{sample}{len(ids)} draft finding{'' if len(ids) == 1 else 's'} available. {readable} of {total} authorized source records contain readable text; readable does not mean reviewed.",
        'highlights': highlights,
        'limitation': compact(workspace['analysis']['status'] + '. Ranked retrieval is not exhaustive. Inspect supporting and contrary passages before relying on wording. No legal determination or sharing approval.', 400),
        'review': {'question': compact(next_review['question'], 320), 'reason': compact(next_review['reason'], 400),
                   'timing': compact(next_review['timing'], 160)}}


def markdown(workspace, *, appendix=None):
    handoff = build(workspace)
    review = handoff['next_review']
    def escape(value):
        text = html.escape(str(value))
        for char in '\\[]()*_`':
            text = text.replace(char, '\\' + char)
        return text

    financial = {p['evidence_id'] for p in workspace.get('financial_review', {}).get('evidence', [])}
    def link(ident):
        return (appendix or ('transaction_appendix.md#evidence-' if ident in financial else 'evidence_appendix.md#evidence-')) + ident
    lines = ['## Your next review', '', escape(review['question']), '',
             '**Why now:** ' + escape(review['reason']), '', '**When:** ' + escape(review['timing']), '']
    lines += [' '.join(f'[Source {n + 1}]({link(i)})' for n, i in enumerate(review['evidence_ids'])), '',
              escape(handoff['boundary']), '']
    return '\n'.join(lines)
