import hashlib
import json

from test_catalog_review import run as run  # fixture with immutable admissions


def test_admission_uses_filesystem_notes_and_explicit_graph_limits(run, text_memory_transport):
    from domain.catalog_planning import planner
    from domain.catalog_store import CatalogStore
    ctx, ref = run
    files = text_memory_transport.scopes.setdefault(('test-memory-job', 'test-runtime-run'), {})
    files['run:lesson-review'] = 'source_scan architecture charge boundary: verify external effects'
    result = planner(ctx, {'context': ref, '_child': {'revision': 0}})
    store = CatalogStore(ctx['run_dir'])
    task = result['child_plan']['steps'][0]['id']
    request = store.read(f'catalog/requests/{task}.json')
    prompt = json.loads(request['prompt'])
    assert any(item['content'].endswith('verify external effects') for item in prompt['runtime_memory']['evidence'])
    assert 'fixture_witness' not in request['prompt']
    assert prompt['architecture_graph']['status'] == 'unavailable'
    assert 'cannot establish dependency' in prompt['architecture_graph']['limitation']
    assert 'memory note cannot replace a graph query' in prompt['instructions']
    # Admission replay is immutable even after a human changes a note.
    files['run:lesson-review'] = 'changed manually'
    assert planner(ctx, {'context': ref, '_child': {'revision': 0}}) == result
    assert store.read(f'catalog/requests/{task}.json') == request


def test_graph_queries_run_alongside_notes_and_keep_source_provenance(tmp_path, monkeypatch):
    from domain.catalog_retrieval import graph_context
    from domain.catalog_store import CatalogStore
    source = 'import storage\n'
    sha = hashlib.sha256(source.encode()).hexdigest()
    snapshot = {'snapshot_id': 'abc123', 'manifest': {'modules': {'payments': {'path': 'payments.py'}}},
                'sources': {'payments.py': {'text': source, 'sha256': sha}}}
    calls = []

    class Graph:
        def __init__(self, *args):
            self.evidence = {'E1': {'path': 'payments.py', 'sha256': sha,
                                  'line_start': 1, 'line_end': 1, 'text': source}}
        def query(self, tool, module):
            calls.append((tool, module))
            return {'tool': tool, 'params': {'module': module}, 'status': 'ok',
                    'rows': [{'source': 'payments', 'target': 'storage', 'evidence_ids': ['E1']}],
                    'result_sha256': 'query-hash', 'limit_note': 'bounded static graph'}
        def evidence_ids(self, result):
            return ['E1']

    monkeypatch.setattr('domain.catalog_retrieval.QuerySession', Graph)
    store = CatalogStore(tmp_path)
    cfg = {'investigation': {'max_queries': 4}}
    packet, spans = graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls', cfg)
    assert calls == [('dependencies', 'payments'), ('calls', 'payments')]
    assert packet['queries'][0]['rows'][0]['target'] == 'storage'
    assert spans[0]['excerpt'] == source and spans[0]['sha256'] == sha
    assert spans[0]['id'].startswith('S-')
    assert len(list((tmp_path / 'catalog/graph').glob('*.json'))) == 2
    graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls', cfg)
    assert len(calls) == 2  # Reuse immutable graph receipts, not rescans or extra model calls.


def test_validated_results_are_remembered_without_mutating_human_edits(run, text_memory_transport):
    from domain.catalog_retrieval import publish_runtime_notes
    from domain.catalog_store import CatalogStore
    ctx, _ = run
    store = CatalogStore(ctx['run_dir'])
    store.finish('task-1', {'task_id': 'task-1', 'kind': 'aspect_analysis', 'status': 'completed',
                          'conclusion': 'Inspect the payment dependency graph', 'claims': []})
    saved = store.read('catalog/context.json')
    publish_runtime_notes(store, saved)
    files = text_memory_transport.scopes[('test-memory-job', 'test-runtime-run')]
    path = next(path for path, text in files.items() if 'Inspect the payment dependency graph' in text)
    assert 'Inspect the payment dependency graph' in files[path]
    files[path] = 'Human correction'
    publish_runtime_notes(store, saved)
    assert files[path] == 'Human correction'


def test_graph_failure_reuses_frozen_memory_compilation_on_retry(run, text_memory_transport, monkeypatch):
    import pytest
    from domain import catalog_retrieval
    from domain.catalog_store import CatalogStore
    ctx, _ = run
    store = CatalogStore(ctx['run_dir'])
    saved = store.read('catalog/context.json')
    snapshot = {'snapshot_id': 'retry-fixture', 'manifest': {'modules': {}}, 'sources': {}}
    task = {'task_id': 'retry-task', 'kind': 'source_scan', 'path': 'payment.py'}
    catalog = {'specs': {}}
    monkeypatch.setattr(catalog_retrieval, 'graph_context', lambda *args: (_ for _ in ()).throw(RuntimeError('graph provider failed')))
    before = sum(c[0] == 'retrieve' for c in text_memory_transport.calls)
    with pytest.raises(RuntimeError, match='graph provider failed'):
        catalog_retrieval.retrieve(store, saved, snapshot, task, catalog)
    cached = store.read('catalog/memory-context/retry-task.json')
    monkeypatch.setattr(catalog_retrieval, 'graph_context', lambda *args: ({'status': 'unavailable'}, []))
    result, _ = catalog_retrieval.retrieve(store, saved, snapshot, task, catalog)
    assert result['runtime_memory'] == cached['packet']
    assert sum(c[0] == 'retrieve' for c in text_memory_transport.calls) == before + 1
    changed = {**snapshot, 'snapshot_id': 'different'}
    with pytest.raises(ValueError, match='replay context changed'):
        catalog_retrieval.retrieve(store, saved, changed, task, catalog)
