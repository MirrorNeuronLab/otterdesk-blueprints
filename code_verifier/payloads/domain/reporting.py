"""Publish every rule, its admitted citations, and explicit static-review limits."""
from collections import Counter
from urllib.parse import quote
from pathlib import Path
import re

from mn_sdk.agent_events import activity_operation, report_activity
from mn_sdk.blueprint_support import source_manifest

from .artifacts import read, save, text
from .publication import stage_outputs
from .rule_review import require_approved_rules


def cell(value):
    value = str(value).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', ' ')
    return re.sub(r'([\\`*\[\]|])', r'\\\1', value)


@activity_operation('Writing the rules report', completed='Rules report saved')
def publish(context):
    capture, rules, verification = read(context, 'capture.json'), read(context, 'rules.json'), read(context, 'verification.json')
    if not (capture['snapshot_id'] == rules['snapshot_id'] == verification['snapshot_id']):
        raise ValueError('Report inputs have different source identities.')
    results = {r['rule_id']: r for r in verification['results']}
    if len(results) != len(verification['results']) or set(results) != {r['id'] for r in rules['rules']}:
        raise ValueError('Every rule must have exactly one verification result.')
    approval = require_approved_rules(context, rules)
    if verification.get('rules_review') != approval:
        raise ValueError('Verification does not match the approved rules.')
    counts = dict(Counter(r['status'] for r in results.values()))
    gaps = rules.get('extraction_gaps', [])
    coverage_note = (f'Partial extraction: {len(gaps)} source sections remain unresolved. '
                     'Missing requirements have not been assessed.' if gaps else
                     'Extraction covered the selected document packets.')
    if not rules['rules']:
        coverage_note += ' No software rules were identified. This report establishes no conformance result.'
    lines = ['# Software rules report', '',
             'Static AI review of a captured source folder. Repository code and tests were not executed. '
             'Pass means the inspected implementation supports the rule within this scope; it is not runtime proof. '
             'Confidence is an uncalibrated AI assessment, capped at 0.85 for static judgments. '
             'Unknown requires more evidence or human review.', '',
             f"Capture: `{capture['snapshot_id']}`. Rules: {len(results)}. "
             f"Pass: {counts.get('pass', 0)}. Fail: {counts.get('fail', 0)}. Unknown: {counts.get('unknown', 0)}.", '',
             'The supervisor approved these exact rules before verification started.', '',
             coverage_note, '',
             '| Rule | Pass or not | Evidence with reference | Confidence (0–1) |',
             '| --- | --- | --- | --- |']
    for rule in rules['rules']:
        result = results[rule['id']]
        references = []
        for evidence in result['evidence']:
            path = evidence['path']
            references.append(f"[{cell(path)}:{evidence['start_line']}–{evidence['end_line']}]"
                              f"(source/{quote(path, safe='/')}#L{evidence['start_line']}) "
                              f"SHA-256 `{evidence['sha256']}`: {cell(evidence['quote'])}")
        lines.append(f"| {cell(rule['id'] + ': ' + rule['statement'])} | {result['status'].capitalize()} | "
                     f"{'; '.join(references) or 'No admissible implementation evidence.'} "
                     f"{cell(result['explanation'])} | {result['confidence']:.2f} |")
    lines += ['', '## Rule origins', '']
    for rule in rules['rules']:
        origin = rule['source']
        lines.append(f"- {cell(rule['id'])}: {cell(rule['origin'])}, "
                     f"{cell(origin['path'])}:{origin['start_line']}–{origin['end_line']}.")
    lines += ['', '## Coverage and limitations', '',
              f"Captured {len(capture['sources'])} UTF-8 files. Excluded {len(capture['omitted'])} entries. "
              'Excluded folders represent whole subtrees. See capture.json and static-analysis.json for the complete inventory and parser gaps.',
              'Missing literal hits, documentation claims, test source, and unresolved call edges do not prove compliance or violation. '
              'Generated rules are candidates for supervisor review; complete extraction is not a guarantee that AI found every requirement.']
    selection = rules.get('documentation_selection', {})
    excluded_documents = selection.get('excluded_documents', [])
    if selection:
        lines += ['', f"Rule document scope: {cell(selection['scope'])}. "
                  f"Selected {len(selection['selected_documents'])} documents; "
                  f"excluded {len(excluded_documents)} generated reports from rule extraction."]
        lines += [f"- {cell(item['path'])}: {cell(item['reason'])}." for item in excluded_documents]
    if gaps:
        lines += ['', '## Unresolved extraction coverage', '',
                  'This report covers the approved candidate rules only. Requirements in the following '
                  'source sections remain unresolved; this is not a complete conformance assessment.', '',
                  '| Source section | Status | Reason |', '| --- | --- | --- |']
        lines += [f"| {cell(gap['path'])}:{gap['start_line']}–{gap['end_line']} | Unknown | {cell(gap['reason'])} |"
                  for gap in gaps]
    refs = [text(context, 'report.md', '\n'.join(lines) + '\n')]
    for path, value in capture['sources'].items():
        text(context, 'source/' + path, value)
    final = {'schema_version': 'mn.software_rules.report.v1', 'snapshot_id': capture['snapshot_id'],
             'rules': rules['rules'], 'results': verification['results'], 'summary': counts,
             'source_execution': False, 'report': 'report.md', 'rules_markdown': 'rules.md',
             'rules_review': approval,
             'assessment_status': 'needs_review' if not rules['rules'] or gaps or counts.get('unknown') else 'complete',
             'coverage': {'documents': rules['extraction_coverage'], 'omitted': capture['omitted'],
                          'extraction_status': rules.get('extraction_status', 'complete'), 'extraction_gaps': gaps,
                          'documentation_selection': selection}}
    refs += [save(context, 'final_artifact.json', final), save(context, 'result.json', final)]
    artifacts = source_manifest(__file__)['contracts']['outputs']['artifacts']
    stage_outputs(context, [item['path'] for item in artifacts
                            if item['artifact_id'] not in {'web_report', 'web_ui'} and
                            (item.get('required') or (Path(context['run_dir']) / item['path']).exists())])
    try:
        from .workspace_web import render
        page = render(final, capture)
        refs.append(text(context, 'web/index.html', page))
        page_path = (Path(context['run_dir']) / 'web/index.html').resolve()
        refs.append(save(context, 'web_ui.json', {'kind': 'output', 'adapter': 'static_html',
            'title': 'Code verification', 'path': str(page_path), 'url': page_path.as_uri(),
            'metadata': {'renderer': 'static_html', 'snapshot': capture['snapshot_id'], 'source_execution': False}}))
        stage_outputs(context, ['web', 'web_ui.json'])
    except Exception as error:
        refs.append(save(context, 'presentation-status.json',
                         {'status': 'unavailable', 'error_type': type(error).__name__}))
        report_activity('The Markdown report is ready. The optional web view could not be created.',
                        kind='action', run_dir=context['run_dir'])
    return {'rules': len(results), 'summary': counts, 'report': 'report.md'}, refs
