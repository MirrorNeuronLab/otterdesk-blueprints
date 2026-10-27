from copy import deepcopy

from test_workspace_output import fixture


def test_summary_keeps_saved_findings_and_coverage_without_inventing_defects(tmp_path):
    from domain.chat_summary import build

    _, workspace = fixture(tmp_path, include_finding=True)
    workspace['coverage']['aspects'] = [
        {'aspect_id': 'selected', 'coverage': 'partial'},
        {'aspect_id': 'omitted', 'coverage': 'not_analyzed'},
    ]
    workspace['source_scope']['unselected_aspects'] = ['omitted']
    before = deepcopy(workspace)
    summary = build(workspace, {'cycles': [['src/a.py', 'src/b.py']]})
    assert workspace == before
    assert summary['overview'] == workspace['executive']
    assert summary['highlights'][0]['title'] == workspace['findings'][0]['statement']
    assert 'Provisional' in summary['highlights'][0]['detail']
    assert '2 files participate' in summary['highlights'][1]['detail']
    assert 'does not establish a defect' in summary['highlights'][1]['detail']
    assert '1/1 selected topics' in summary['limitation']
    assert summary['status'] == 'Review incomplete'


def test_empty_static_review_and_long_source_text_stay_bounded_and_honest(tmp_path):
    from domain.chat_summary import build

    _, workspace = fixture(tmp_path)
    summary = build(workspace)
    assert summary['status'] == 'Static analysis only'
    assert summary['highlights'][0]['title'] == 'Review the captured scope'
    assert 'does not establish architectural health' in summary['highlights'][0]['detail']
    workspace['executive'] = 'source context ' * 300
    workspace['findings'] = [{'statement': 'long title ' * 80, 'status': 'supported',
        'confidence': 'medium', 'next_decision': 'inspect first ' * 100}] * 20
    summary = build(workspace)
    assert len(summary['overview']) <= 600
    assert len(summary['highlights']) <= 3
    assert all(len(row['title']) <= 180 and len(row['detail']) <= 320 for row in summary['highlights'])
