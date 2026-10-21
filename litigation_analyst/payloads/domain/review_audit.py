"""Disclose actual packet coverage and consistency independently of AI acceptance."""
import json


def attach(workspace, context, documents):
    allowed = {d.source_id for d in documents}
    rows = []
    for stage in ('assessment', 'review'):
        for path in sorted((context.store.run_dir / 'case/rounds').glob(f'r*-{stage}.json')):
            value = json.loads(path.read_text())
            assessment_path = path.with_name(path.name.removesuffix('-review.json') + '-assessment.json') if stage == 'review' else path
            assessment = json.loads(assessment_path.read_text()) if assessment_path.is_file() else {}
            coverage = value.get('evidence_review_coverage', {})
            dispatched = value.get('model_dispatched', False)
            rows.append({'task':path.stem, 'stage':stage,
                'counsel_issue_ids':assessment.get('counsel_issue_ids', []),
                'model_dispatched':dispatched,
                'admitted_source_ids':[s for s in coverage.get('admitted_source_ids', []) if s in allowed and dispatched],
                'complete_source_ids':[s for s in coverage.get('complete_source_ids', []) if s in allowed and dispatched]})
    assessed = sorted({s for r in rows if r['stage']=='assessment' for s in r['admitted_source_ids']})
    reviewed = sorted({s for r in rows if r['stage']=='review' for s in r['admitted_source_ids']})
    workspace['coverage'].update({'model_packets':rows, 'assessor_source_ids':assessed,
        'reviewer_source_ids':reviewed, 'unreviewed_source_ids':sorted(allowed-set(reviewed)),
        'review_definition':'Source text admitted to actual model packets, not proof of comprehension or attorney review'})
    for issue in workspace.get('counsel_issues', []):
        issue['assessor_source_ids'] = sorted({s for r in rows if r['stage']=='assessment' and issue['id'] in r['counsel_issue_ids'] for s in r['admitted_source_ids']})
        issue['reviewer_source_ids'] = sorted({s for r in rows if r['stage']=='review' and issue['id'] in r['counsel_issue_ids'] for s in r['admitted_source_ids']})
        if issue['hypothesis_ids']:
            issue['status'] = 'Enquiry attempted; see admitted source coverage. Requires attorney review.'
    from .review_packets import consistency_checks
    report = {'findings':workspace['findings']}
    checks = consistency_checks(report, workspace['financial_review'])
    path = context.store.run_dir / 'case/consistency_review.json'
    if path.is_file():
        visible = {e['evidence_id'] for e in workspace['evidence']}
        checks.extend(c for c in json.loads(path.read_text()).get('checks', [])
                      if set(c.get('evidence_ids', [])) <= visible)
    blocked = {c['finding_id'] for c in checks}
    workspace['findings'] = [f for f in workspace['findings'] if f['id'] not in blocked and f['model_finding_id'] not in blocked]
    workspace['consistency'] = {'status':'needs_review' if checks else 'no_mechanical_conflict_detected',
        'checks':checks, 'withheld_finding_ids':sorted(blocked),
        'qualification':'Limited explicit-absence guard. Model and attorney semantic review remain necessary.'}
    # Bind the changed visible basis to human-review identity.
    from mn_temporal_graph_skill import fingerprint
    workspace['snapshot_id'] = fingerprint([workspace['snapshot_id'], workspace['coverage'], workspace['consistency']])
    return workspace
