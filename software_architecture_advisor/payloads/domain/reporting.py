"""Check frozen evidence before publishing the review and follow-up tasks."""
import hashlib
import json
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from .events import audit_scope, emit
from .investigator import validate_assessment
from .prompts import render_prompts
from .rendering import render_markdown


def verify_evidence(report, run_dir):
    snapshot = json.loads((run_dir / 'snapshot.json').read_text())
    if report['snapshot'] != snapshot['id']:
        raise ValueError('Report snapshot differs from captured input')
    directory = run_dir / 'evidence/snapshots' / snapshot['id']
    sources = json.loads((directory / 'sources.json').read_text())
    if set(sources) != set(snapshot['sources']):
        raise ValueError('Source snapshot inventory mismatch')
    for path, source in sources.items():
        if hashlib.sha256(source['text'].encode()).hexdigest() != snapshot['sources'][path] or source['sha256'] != snapshot['sources'][path]:
            raise ValueError('Source snapshot hash mismatch')
    for evidence in report['evidence'].values():
        if evidence['kind'] == 'observed_history':
            # The collector retains the exact anchored log and hash in its records.
            records = list((directory / 'layers/records').glob('*.json'))
            if not any(hashlib.sha256(json.loads(p.read_text())['details'].get('raw_log', '').encode()).hexdigest() == evidence['sha256'] for p in records):
                raise ValueError('History evidence has no matching anchored log')
            continue
        source = sources.get(evidence['path'])
        if source is None or source['sha256'] != evidence['sha256']:
            raise ValueError('Evidence source hash mismatch')
        text = source['text']
        span = text[evidence['start_offset']:evidence['end_offset']] if 'start_offset' in evidence else ''.join(text.splitlines(keepends=True)[evidence['line_start']-1:evidence['line_end']])
        if span != evidence['text']:
            raise ValueError('Evidence span differs from frozen source')
    if 'decisions' in report:
        from .evidence_validation import verify_packets
        verify_packets(report)
    for finding in report['findings']:
        if finding['status'] == 'assessed':
            validate_assessment(finding['assessment'], finding['packet'])
    for decision in report.get('decisions', []):
        validate_assessment(decision, decision['packet'])
    if report.get('decision'):
        validate_assessment(report['decision'], report['decision']['packet'])


def publish_review(context, *, llm_client=None):
    run_dir = Path(context['run_dir'])
    report = json.loads((run_dir / 'investigation.json').read_text())
    if report['status'] not in {'review_draft', 'partial'}:
        raise ValueError('Cannot publish an unsuccessful investigation as a review')
    verify_evidence(report, run_dir)
    outputs = {'report.md': render_markdown(report), 'suggestive_prompts.md': render_prompts(report),
               'knowledge.json': json.dumps(report['knowledge'], indent=2), 'report.json': json.dumps(report, indent=2)}
    with audit_scope(run_dir):
        for name, text in outputs.items():
            (run_dir / name).write_text(text, encoding='utf-8')
            emit('artifact.write.completed', path=name, bytes=(run_dir/name).stat().st_size)
        index = {'status': report['status'], 'snapshot': report['snapshot'],
                 'report': 'report.md', 'prompts': 'suggestive_prompts.md',
                 'data': 'report.json', 'evidence': 'evidence/', 'events': 'events.log'}
        (run_dir / 'review_index.json').write_text(json.dumps(index, indent=2), encoding='utf-8')
    refs = [artifact_reference(name, path) for name, path in [('report','report.md'),
            ('suggestive_prompts','suggestive_prompts.md'), ('knowledge','knowledge.json'),
            ('report_data','report.json'), ('review_index','review_index.json')]]
    return {'status': report['status'], 'report': refs[0], 'review_index': refs[-1]}, refs
