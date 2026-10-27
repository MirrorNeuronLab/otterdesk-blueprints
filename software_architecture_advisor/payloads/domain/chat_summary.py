"""Bounded Chat presentation of the same saved workspace used by the report."""


def _text(value, maximum):
    text = ' '.join(str(value or '').split())
    return text if len(text) <= maximum else text[:maximum - 1].rsplit(' ', 1)[0] + '…'


def build(workspace, static=None):
    excluded = set(workspace['source_scope'].get('unselected_aspects', []))
    topics = [row for row in workspace['coverage'].get('aspects', [])
              if row['aspect_id'] not in excluded]
    reviewed = sum(row.get('coverage') in {'partial', 'complete_for_stated_scope'} for row in topics)
    status = ('Static analysis only' if not reviewed and not workspace['terminal'].get('usage', {}).get('catalog_models')
              else 'Review incomplete' if workspace['status'] == 'partial' else 'Review draft')
    highlights = []
    findings = sorted(workspace['findings'], key=lambda row: row['status'] != 'supported')
    for finding in findings[:2]:
        highlights.append({'title': _text(finding['statement'], 180),
            'detail': _text(f"{finding['status'].replace('_', ' ').capitalize()} · "
                f"{finding['confidence']} confidence. {finding.get('next_decision', '')}", 320)})
    cycles = static['cycles'] if static is not None else workspace['cycles']
    if cycles:
        cycle = sorted(cycles, key=lambda row: (-len(row), row))[0]
        highlights.append({'title': 'Review the dependency cycle',
            'detail': _text(f"{len(cycle)} {'files' if static is not None else 'modules'} participate, including {cycle[0]}. "
                'This is an investigation candidate; a cycle alone does not establish a defect.', 320)})
    elif not highlights:
        highlights.append({'title': 'Review the captured scope',
            'detail': 'No supported finding or dependency cycle was recorded. Missing evidence does not establish architectural health.'})
    return {'schema_version': 'otterdesk.report-summary.v1', 'status': status,
        'overview': _text(workspace['executive'], 600), 'highlights': highlights,
        'limitation': _text(f"{len(workspace['files'])} source files captured · {reviewed}/{len(topics)} selected topics have model analysis. "
            'Runtime behavior and proposed changes still need verification.', 400)}
