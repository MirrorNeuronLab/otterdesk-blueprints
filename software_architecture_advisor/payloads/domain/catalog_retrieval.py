"""Owner-side runtime notes plus source-backed architecture graph retrieval."""
import json
import re

from mn_sdk.file_memory import runtime_file_memory
from .catalog_store import fingerprint
from .graph import QuerySession
from .catalog import LayerUnavailable
from .review_prompts import evidence_record


def _focus(task, catalog, goal):
    spec = catalog['specs'].get(task.get('aspect_id'), {})
    # Put the current aspect/module first; generic goals must not crowd out task terms.
    return ' '.join(str(x) for x in [task.get('path', ''), task.get('reason', ''),
                     spec.get('title', ''), spec.get('question', ''), task['kind'], goal[:500]] if x)


def graph_context(store, snapshot, task, focus, config):
    modules = snapshot['manifest'].get('modules', {})
    if not modules:
        return {'status': 'unavailable', 'queries': [], 'incomplete': True,
                'limitation': 'No structural modules in this snapshot; text memory cannot establish dependency relationships.'}, []
    terms = set(re.findall(r'[\w]+', focus.lower()))
    names = sorted(modules, key=lambda n: (
        modules[n].get('path') != task.get('path'),
        -len(set(re.findall(r'[\w]+', n.lower())) & terms), n))[:2]
    # Existing allowlisted read-only views: dependencies and a focused aspect view.
    view = ('calls' if terms & {'call', 'calls', 'function'} else
            'state' if terms & {'state', 'database', 'transaction'} else
            'deployment' if terms & {'deployment', 'container', 'service'} else 'cycles')
    requested = [('dependencies', n) for n in names] + [(view, names[0])]
    receipts, witnesses = [], {}
    session = None
    for tool, module in requested:
        key = fingerprint([snapshot['snapshot_id'], tool, module])
        path = f'catalog/graph/{key}.json'
        if store.path(path).exists():
            cached = store.read(path)
        elif len(list(store.path('catalog/graph').glob('*.json'))) >= config['investigation']['max_queries']:
            receipts.append({'tool': tool, 'module': module, 'status': 'budget_exhausted', 'rows': []})
            continue
        else:
            if session is None:
                session = QuerySession(store.root / 'evidence', config, snapshot['snapshot_id'])
            try:
                result = session.query(tool, module)
            except LayerUnavailable:
                result = {'tool': tool, 'params': {'module': module}, 'status': 'unavailable',
                          'rows': [], 'limit_note': 'Required source-backed graph layer is unavailable.'}
            # Provider/corruption failures remain errors, not empty graphs.
            used = session.evidence_ids(result)
            cached = {'query': result, 'evidence': {i: session.evidence[i] for i in used}}
            store.write(path, cached)
        result = cached['query']
        receipts.append({k: result[k] for k in ['tool', 'params', 'status', 'rows', 'result_sha256', 'limit_note'] if k in result})
        witnesses.update(cached['evidence'])
    evidence = []
    for witness in witnesses.values():
        source = snapshot['sources'][witness['path']]
        lines = source['text'].splitlines(keepends=True)
        start = sum(map(len, lines[:witness['line_start']-1]))
        end = sum(map(len, lines[:witness['line_end']]))
        if source['sha256'] != witness['sha256'] or source['text'][start:end] != witness['text']:
            raise ValueError('Graph witness differs from frozen source')
        evidence.append(evidence_record({'path': witness['path'], 'sha256': source['sha256'],
                        'start_offset': start, 'end_offset': end, 'start_line': witness['line_start'],
                        'end_line': witness['line_end'], 'text': witness['text']}))
    packet = {'status': 'queried', 'queries': [], 'incomplete': True,
              'limitation': 'Static source-backed graph samples, not runtime behavior or proof of absence. Cite only supplied S- source spans; full query receipts are in catalog/graph.'}
    for receipt in receipts:
        # Preserve whole rows within a fixed prompt share. Full results stay in receipts.
        compact = {**receipt, 'rows': [], 'rows_omitted': len(receipt['rows'])}
        packet['queries'].append(compact)
        if len(json.dumps(packet).encode()) > 3500:
            packet['queries'].pop()
            break
        for row in receipt['rows']:
            compact['rows'].append(row)
            if len(json.dumps(packet).encode()) > 3500:
                compact['rows'].pop()
                break
            compact['rows_omitted'] -= 1
    return packet, evidence


def retrieve(store, saved, snapshot, task, catalog):
    config = saved['request']['retrieval_config']
    focus = _focus(task, catalog, saved['request']['goal'])
    memory = runtime_file_memory(config, principal='architecture', scope=saved['request']['memory_scope'])
    notes = {'notes': [], 'incomplete': False, 'status': 'disabled'}
    if memory is not None:
        try:
            memory.initialize()
            notes = memory.retrieve(focus)
        finally:
            memory.close()
    if config.get('offline'):
        graph = {'status': 'offline', 'queries': [], 'incomplete': True}
        evidence = []
    else:
        graph, evidence = graph_context(store, snapshot, task, focus, config)
    return {'runtime_memory': notes, 'architecture_graph': graph}, evidence


def publish_runtime_notes(store, saved):
    memory = runtime_file_memory(saved['request']['retrieval_config'], principal='architecture',
                                 scope=saved['request']['memory_scope'])
    if memory is None:
        return
    try:
        for task_id, result in store.results().items():
            marker = f'catalog/memory/{task_id}.json'
            if store.path(marker).exists():
                continue
            content = {k: result[k] for k in ['task_id', 'kind', 'status', 'aspect_id', 'scope',
                       'conclusion', 'limitations', 'analysis_verdict', 'claims', 'observations'] if k in result}
            ref = memory.remember(task_id, title=f"Architecture {result.get('aspect_id', task_id)} {result['kind']}",
                                  content=content, source_ref=f'catalog/results/{task_id}.json')
            store.write(marker, {'path': ref['path']})
    finally:
        memory.close()
