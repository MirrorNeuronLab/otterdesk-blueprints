"""Record-grounded reading briefs, graph provenance and frozen-run preservation."""
from copy import deepcopy
from dataclasses import asdict
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest
from test_litigation_analyst import BLUEPRINT, modules


@pytest.fixture
def workspace(modules):
    from domain.models import CaseDocument
    from domain.financial_review import build
    from domain.temporal_evidence import project

    root = BLUEPRINT / 'examples/approval_reversal_case'
    matter = json.loads((root / 'matter.json').read_text())
    documents = []
    for path in sorted((root / 'inputs').iterdir()):
        if path.name.startswith('07_'):
            continue
        text = path.read_text()
        documents.append(CaseDocument('case:' + path.name, path.name,
            'message/rfc822' if path.suffix == '.eml' else 'text/plain',
            hashlib.sha256(text.encode()).hexdigest(), len(text.encode()), text, 'case'))
    financial = build(matter, documents, {})
    temporal = project(documents, 'synthetic-matter')
    evidence = financial['evidence'] + [p for event in temporal['events'] for p in event['evidence_refs']]
    return {'title': 'Synthetic record review', 'snapshot_id': 'frozen-snapshot', 'sources': [
        {**asdict(d), 'original_sha256': d.content_sha256, 'original_included': False} for d in documents],
        'evidence': evidence, 'temporal': temporal, 'financial_review': financial,
        'matter_scope': {'intended_decision': matter['intended_decision']},
        'analysis': {'status': 'Partial review', 'scope': 'Frozen synthetic records'},
        'goal': 'Reconcile transaction records', 'gaps': [], 'findings': [
            {'id': 'bad-approval', 'title': 'No visible written authorization',
             'assessment': 'No written approval is visible for TX-104.', 'limitations': 'Partial review'},
            {'id': 'bad-ledger', 'title': 'Ledger missing',
             'assessment': 'No ledger or reversal records supplied.', 'limitations': 'Partial review'},
            {'id': 'qualified', 'title': 'Bank settlement unresolved',
             'assessment': 'The accounting net does not determine external bank settlement.',
             'limitations': 'No legal conclusion.', 'supporting_evidence': financial['transactions'][0]['evidence_ids'],
             'counter_evidence': []}]}


def test_reading_brief_withholds_conflicting_drafts_and_preserves_originals(workspace):
    from domain.workspace_review import attach
    before = deepcopy(workspace['findings'])
    result = attach(workspace)
    assert result['findings'] == before
    assert set(result['reading_review']['withheld_finding_ids']) == {'bad-approval', 'bad-ledger'}
    brief = result['reading_reports'][0]['markdown']
    assert 'USD 12500.00' in brief and 'USD 8000.00' in brief and 'USD 4500.00' in brief
    assert 'Posting / reversal net: USD 0.00' in brief
    retained = brief.split('## Retained draft findings')[1].split('## Next review work')[0]
    assert 'No written approval is visible' not in retained
    assert 'Bank settlement unresolved' in retained
    assert {t['status'] for t in result['reading_tasks']} == {'Internal reread', 'Evidence check'}
    assert all(t['owner'] == 'Unassigned' for t in result['reading_tasks'])


def test_graph_links_named_addresses_events_and_exact_financial_sources(workspace):
    from domain.workspace_review import attach
    result = attach(workspace)
    graph = result['case_map']
    nodes = {n['id']: n for n in graph['nodes']}
    assert {n['label'] for n in nodes.values() if n['kind'] == 'correspondent'} == {'Elena Cruz', 'Maya Chen', 'Omar Reed'}
    assert sum(n['kind'] == 'communication' for n in nodes.values()) == 3
    assert sum(n['kind'] == 'financial_record' for n in nodes.values()) == 5
    reversal = next(n for n in nodes.values() if n['label'].startswith('Reversal'))
    assert reversal['date'] == '2025-01-09'
    assert all(r['source'] in nodes and r['target'] in nodes and r['evidence_ids'] for r in graph['edges'])
    evidence = {p['evidence_id']: p for p in result['evidence']}
    for edge in graph['edges']:
        assert set(edge['evidence_ids']) <= evidence.keys()
    assert 'causation' in graph['definition']
    assert '07_privileged_advice' not in json.dumps(graph)


@pytest.mark.parametrize('tamper', ['text', 'offset', 'financial_quote', 'amount'])
def test_reading_view_rejects_broken_source_bindings(workspace, tamper):
    from domain.workspace_review import attach
    if tamper == 'text':
        workspace['sources'][0]['text'] += 'Changed'
    elif tamper == 'offset':
        workspace['evidence'][0]['start_offset'] += 1
    elif tamper == 'financial_quote':
        workspace['financial_review']['events'][0]['quote'] = 'Invented source claim'
    else:
        workspace['financial_review']['events'][0]['amount'] = '99000.00'
    with pytest.raises(ValueError):
        attach(workspace)


def test_reading_totals_are_recomputed_from_source_bound_records(workspace):
    from domain.workspace_review import attach
    workspace['financial_review']['transactions'][0]['posting_reversal_net'] = '99000.00'
    result = attach(workspace)
    assert result['financial_review']['transactions'][0]['posting_reversal_net'] == '0.00'


def test_render_copy_never_modifies_the_frozen_run(workspace, tmp_path):
    spec = importlib.util.spec_from_file_location('litigation_render_review', BLUEPRINT / 'render_review.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    run = tmp_path / 'frozen'
    (run / 'case').mkdir(parents=True)
    path = run / 'case/workspace.json'
    path.write_text(json.dumps(workspace))
    original = path.read_bytes()
    result = module.render_copy(run, tmp_path / 'reading-copy')
    assert result.is_file()
    assert (result.parent / 'counsel-review-brief.md').is_file()
    assert path.read_bytes() == original
    assert sorted(p.name for p in run.iterdir()) == ['case']
    with pytest.raises(ValueError, match='separate'):
        module.render_copy(run, run / 'review')
    with pytest.raises(FileExistsError):
        module.render_copy(run, result.parent)


def test_optional_reading_failure_preserves_authoritative_workspace(workspace, tmp_path, monkeypatch):
    from domain import workspace_review, workspace_web
    run = tmp_path / 'run'
    (run / 'case').mkdir(parents=True)
    (run / 'web').mkdir()
    (run / 'web/index.html').write_text('Stale broader projection')
    def fail(_):
        raise RuntimeError('Presentation failed')
    monkeypatch.setattr(workspace_review, 'attach', fail)
    status, _ = workspace_web.publish({'run_dir': run, 'config': {}}, workspace)
    assert status['status'] == 'Unavailable'
    assert json.loads((run / 'case/workspace.json').read_text())['snapshot_id'] == workspace['snapshot_id']
    assert not (run / 'web').exists()
