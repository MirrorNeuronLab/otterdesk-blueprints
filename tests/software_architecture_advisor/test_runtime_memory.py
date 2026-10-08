import hashlib
import json

from test_catalog_review import run as run  # fixture with immutable admissions


def test_file_scan_skips_memory_but_aspect_review_can_recall_notes(run, text_memory_transport):
    from domain.catalog_planning import planner
    from domain.catalog_store import CatalogStore
    from domain.catalog_knowledge import publish_runtime_notes
    ctx, ref = run
    store = CatalogStore(ctx['run_dir'])
    store.finish('lesson-review',{'task_id':'lesson-review','kind':'source_scan',
        'status':'completed','conclusion':'Architecture charge boundary: verify external effects',
        'claims':[],'observations':[]})
    publish_runtime_notes(store,store.read('catalog/context.json'))
    files = text_memory_transport.scopes[('test-memory-job','test-runtime-run')]
    note = store.read('catalog/memory/lesson-review.json')['source_id']
    result = planner(ctx, {'context': ref, '_child': {'revision': 0}})
    store = CatalogStore(ctx['run_dir'])
    task = result['child_plan']['steps'][0]['id']
    request = store.read(f'catalog/requests/{task}.json')
    prompt = json.loads(request['prompt'])
    assert 'runtime_memory' not in prompt
    from domain.catalog_retrieval import retrieve
    from domain.catalog_contract import load_snapshot
    context, _ = retrieve(store, store.read('catalog/context.json'), load_snapshot(ctx['run_dir']),
        {'task_id':'aspect-history','kind':'aspect_analysis'}, {'specs':{}})
    assert any('verify external effects' in item['content'] and item['content'].startswith('# Architecture')
               for item in context['runtime_memory']['evidence'])
    assert 'fixture_witness' not in request['prompt']
    assert prompt['architecture_graph']['status'] == 'entity_unresolved'
    assert prompt['architecture_graph']['unresolved'] == ['entity_unresolved']
    assert 'memory note cannot replace a graph query' in prompt['instructions']
    # Admission replay is immutable even after a human changes a note.
    files[note] = 'changed manually'
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
    monkeypatch.setattr('domain.context_traversal.query_paths',
        lambda session, plan, focus: session.query('context_paths', plan['modules'][0]))
    store = CatalogStore(tmp_path)
    from domain.catalog_sources import publish_inputs
    request = {'memory_scope':{'job_id':'test-memory-job','run_id':'test-memory-run'},
        'retrieval_config':{'text_memory':{'enabled':True,'max_results':6,'max_context_bytes':32768}}}
    publish_inputs(store, request, snapshot)
    cfg = {'investigation': {'max_queries': 4}}
    packet, spans = graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls', cfg, request=request)
    assert calls == [('context_paths', 'payments'), ('calls', 'payments')]
    assert packet['queries'][0]['rows'][0]['target'] == 'storage'
    assert spans[0]['excerpt'] == source and spans[0]['sha256'] == sha
    assert spans[0]['id'].startswith('S-')
    assert packet['queries'][0]['rows'][0]['source_evidence_ids'] == [spans[0]['id']]
    assert len(list((tmp_path / 'catalog/graph').glob('*.json'))) == 2
    graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls', cfg, request=request)
    assert len(calls) == 2  # Reuse immutable graph receipts, not rescans or extra model calls.


def test_retry_plan_uses_cross_layer_call_state_and_test_views(architecture_paths):
    from domain.context_query_plan import views
    assert views('Retry idempotency and duplicate charge risk') == ['call_state', 'test_call_links', 'control_flow']
    assert views('function calls') == ['calls']
    assert views('test coverage') == ['test_call_links', 'tests']
    assert views('unknown concern') == []


def test_graph_replay_preserves_witness_order_and_rendered_context(tmp_path, monkeypatch):
    from domain.catalog_retrieval import graph_context
    from domain.catalog_store import CatalogStore
    from domain.review_prompts import build_prompt
    source = 'import storage\nreturn storage.value\n'
    sha = hashlib.sha256(source.encode()).hexdigest()
    snapshot = {'snapshot_id': 'abc123', 'manifest': {'modules': {'payments': {'path': 'payments.py'}}},
                'sources': {'payments.py': {'text': source, 'sha256': sha}}}
    calls = []

    class Graph:
        def __init__(self, *args):
            # Cold graph discovery and sorted committed JSON have different
            # mapping order. Neither may change the next prompt's selection.
            self.evidence = {id: {'path': 'payments.py', 'sha256': sha,
                'line_start': line, 'line_end': line, 'text': text}
                for id, line, text in [('EZ', 1, 'import storage\n'), ('EA', 2, 'return storage.value\n')]}

        def query(self, tool, module):
            calls.append((tool, module))
            return {'tool': tool, 'params': {'module': module}, 'status': 'ok',
                'rows': [{'source': 'payments', 'target': 'storage', 'evidence_ids': ['EZ', 'EA']}],
                'result_sha256': 'query-hash', 'limit_note': 'bounded static graph'}

        def evidence_ids(self, result):
            return ['EZ', 'EA']

    monkeypatch.setattr('domain.catalog_retrieval.QuerySession', Graph)
    monkeypatch.setattr('domain.context_traversal.query_paths',
        lambda session, plan, focus: session.query('context_paths', plan['modules'][0]))
    store = CatalogStore(tmp_path)
    from domain.catalog_sources import publish_inputs
    request = {'memory_scope':{'job_id':'test-memory-job','run_id':'test-memory-run'},
        'retrieval_config':{'text_memory':{'enabled':True,'max_results':6,'max_context_bytes':32768}}}
    publish_inputs(store, request, snapshot)
    first = graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls',
                          {'investigation': {'max_queries': 4}}, request=request)
    replay = graph_context(store, snapshot, {'path': 'payments.py'}, 'function calls',
                           {'investigation': {'max_queries': 4}}, request=request)
    assert first == replay
    assert len(calls) == 2
    prompts = [build_prompt({'kind': 'executive_synthesis', 'task_id': 'synthesis'},
        {'specs': {}, 'conventions': ''}, snapshot, {}, {}, 8000, {},
        retrieval={'architecture_graph': packet}, graph_evidence=spans)['prompt']
        for packet, spans in (first, replay)]
    assert prompts[0] == prompts[1]


def test_graph_rows_are_omitted_when_whole_source_witnesses_cannot_fit(architecture_paths):
    from domain.review_prompts import build_prompt
    evidence = {'id': 'S-cross-file', 'path':'counter.py', 'sha256':'a'*64,
                'start_offset':0,'end_offset':12000,'start_line':1,'end_line':1,'excerpt':'x'*12000}
    graph = {'queries':[{'tool':'call_state','rows':[{'caller':'charge','writer':'persist',
                        'source_evidence_ids':['S-cross-file']}], 'rows_omitted':0}]}
    task = {'kind':'executive_synthesis','task_id':'synthesis'}
    admission = build_prompt(task,{'specs':{},'conventions':''},
                            {'sources':{},'snapshot_id':'s'}, {},{},8000,{},
                            retrieval={'architecture_graph':graph},graph_evidence=[evidence])
    value = json.loads(admission['prompt'])
    assert value['architecture_graph']['queries'][0]['rows'] == []
    assert value['architecture_graph']['queries'][0]['rows_omitted'] == 1
    assert value['evidence'] == []


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
    from domain.catalog_contract import load_snapshot
    snapshot = load_snapshot(ctx['run_dir'])
    task = {'task_id': 'retry-task', 'kind': 'aspect_analysis', 'path': 'payment.py'}
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


def test_self_contained_architecture_tasks_do_not_open_memory(tmp_path, monkeypatch):
    from domain import catalog_retrieval
    from domain.catalog_store import CatalogStore
    monkeypatch.setattr(catalog_retrieval, 'runtime_text_memory',
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('No recall for this task')))
    saved = {'request': {'retrieval_config': {'offline': True}, 'goal': 'review supplied files'}}
    for kind in ['source_scan', 'evidence_followup', 'section_synthesis', 'executive_synthesis']:
        packet, evidence = catalog_retrieval.retrieve(CatalogStore(tmp_path), saved, {},
            {'task_id': kind, 'kind': kind}, {'specs': {}})
        assert 'runtime_memory' not in packet
        assert evidence == []
