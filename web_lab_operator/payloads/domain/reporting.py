"""Publish selected run evidence through existing SDK publication primitives."""

import json
from hashlib import sha256

from mn_sdk.blueprint.outputs import publish_artifact_bundle, publish_files
from mn_sdk_common.publication import ArtifactWrite
from mn_web_report_skill import render_report_markdown

LIMITATIONS = [
    'Simulation only: no physical robot, samples or instruments are connected.',
    'Observed volumes are PyLabRobot bookkeeping, not measured liquid volumes or experimental results.',
    'Liquid labels describe the supplied inventory; chemistry, contamination, evaporation, collisions and assay outcomes are not modeled.',
    'The model may misinterpret Markdown. Review the saved plan and its numbered-instruction references.',
    'Adaptation selects a predeclared source with the same liquid and enough volume. Goals, order and transfer amounts cannot change.',
    'Waits advance virtual procedure time; they do not simulate reaction kinetics or incubation.',
    'Membrane recall is bounded historical simulation evidence. Current procedure rules and tracked state remain authoritative; missing history is not proof of absence.',
]


def publish(block, inputs):
    value = block.read_checkpoint(inputs['simulation']['simulation'], expected_path='simulation-checkpoint.json')
    trace = block.read_evidence(value['trace'])
    block.read_evidence(value['plan'])
    memory = block.read_evidence(value['memory'])
    final = {key: value[key] for key in ['status', 'simulation_only', 'procedure_sha256', 'summary',
                                        'reason', 'steps_completed', 'steps_total', 'adaptations', 'goals',
                                        'assumptions', 'unresolved']}
    final.update(schema_version='mn.web_lab.review.v1', limitations=LIMITATIONS,
                 risks=[{'step': event['step']['id'], **risk} for event in trace['events']
                        for risk in event.get('risks', [])],
                 memory={'enabled': memory['enabled'], 'scope': memory['scope'], 'artifact': 'memory.json',
                         'records_saved': len(memory['records']),
                         'evidence_supplied': sum(len(item['packet']['evidence']) for item in memory['recalls'])},
                 source_refs=['procedure.md', 'plan.json', 'trace.json', 'simulation.json', 'memory.json'])
    document = {'title': 'Web lab review', 'summary': value['summary'], 'sections': [
        {'id': 'outcome', 'title': 'Observed outcome', 'blocks': [
            {'type': 'paragraph', 'text': value['reason']},
            {'type': 'metric', 'label': 'Procedure status', 'value': value['status'].replace('_', ' ')},
            {'type': 'metric', 'label': 'Completed steps', 'value': f"{value['steps_completed']} / {value['steps_total']}"},
            {'type': 'paragraph', 'text': f"Adaptations: {value['adaptations']}."}]},
        {'id': 'goals', 'title': 'Final volume goals', 'blocks': [
            {'type': 'table', 'columns': ['Well', 'Expected (uL)', 'Observed (uL)', 'Tolerance (uL)', 'Met'],
             'rows': [[g['well'], g['volume_ul'], g['observed_ul'], g['tolerance_ul'], g['met']] for g in value['goals']]}]},
        {'id': 'steps', 'title': 'Procedure evidence', 'blocks': [
            {'type': 'table', 'columns': ['Step', 'Instruction lines', 'Decision', 'Observed result', 'Reason'],
             'rows': [[e['step']['id'], ', '.join(map(str, e['step']['instruction_lines'])),
                       e['decision']['decision'], 'Passed' if e['outcome']['passed'] else 'Needs review',
                       e['error'] or ('The volume check did not pass.' if e['action'] is not None
                                     and not e['outcome']['passed'] else e['decision']['reason'])]
                      for e in trace['events']]}]},
        {'id': 'review', 'title': 'Review before another run', 'blocks': [
            {'type': 'paragraph', 'text': text} for text in value['assumptions'] + value['unresolved']]},
        {'id': 'risks', 'title': 'Tracked risks', 'blocks': [
            {'type': 'warning', 'text': risk['message']} for risk in final['risks']]},
        {'id': 'memory', 'title': 'Memory supplied to decisions', 'blocks': [
            {'type': 'paragraph', 'text': ('Job-private Membrane history was enabled. Inspect memory.json for complete '
                'query witnesses, source citations and saved outcome receipts.' if memory['enabled'] else
                'Memory was explicitly disabled for this run. No experience was retrieved or saved.')},
            {'type': 'table', 'columns': ['Phase', 'Recall status', 'Evidence supplied', 'Omitted'],
             'rows': [[item['phase'], item['packet']['status'], len(item['packet']['evidence']),
                       item['packet'].get('omitted_count', 0)] for item in memory['recalls']]}]},
        {'id': 'limits', 'title': 'Simulation limits', 'blocks': [
            {'type': 'warning', 'text': text} for text in LIMITATIONS]},
    ]}
    encoded = json.dumps(final, ensure_ascii=False, sort_keys=True, allow_nan=False).encode()
    revision = sha256(encoded).hexdigest()

    def page():
        from .presentation import render
        return render(final, trace).encode()

    def handle():
        from mn_sdk_web_ui import static_run_report_handle
        return json.dumps(static_run_report_handle(block.store.run_dir, 'web/index.html',
                          title='Web lab replay', optional=True)).encode()

    writes = [ArtifactWrite('final_artifact', 'final_artifact.json', encoded, kind='json', authoritative=True),
              ArtifactWrite('result', 'result.json', encoded, kind='json', authoritative=True),
              ArtifactWrite('report', 'report.md', render_report_markdown(document).encode(), kind='markdown')]
    for identifier, reference in [('procedure', value['procedure']), ('plan', value['plan']), ('trace', value['trace'])]:
        writes.append(ArtifactWrite(identifier, reference['path'], block.store.read_bytes(reference), kind=reference['kind']))
    writes.append(ArtifactWrite('simulation', 'simulation.json',
                              block.store.read_bytes(inputs['simulation']['simulation_artifact']), kind='json'))
    writes.append(ArtifactWrite('memory', 'memory.json', block.store.read_bytes(value['memory']), kind='json'))
    writes.extend([
        ArtifactWrite('web_report', 'web/index.html', page, kind='html', required=False, revision=revision),
        ArtifactWrite('web_ui', 'web_ui.json', handle, kind='json', required=False, revision=revision, mode=0o644),
    ])
    receipt = publish_artifact_bundle(block, writes, receipt_path=block.root + '/publication.json')
    publication = publish_files(block, [ArtifactWrite(
        item['id'], item['reference']['path'], block.store.read_bytes(item['reference']),
        kind=item['reference']['kind'], required=item['required']) for item in receipt['artifacts']], name='web_lab_review')
    return {'status': value['status'], 'published_files': publication, 'warnings': receipt['warnings']}
