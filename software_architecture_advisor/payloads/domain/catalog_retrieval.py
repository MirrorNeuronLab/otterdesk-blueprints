"""Owner-side runtime notes plus source-backed architecture graph retrieval."""
import json
from collections import Counter

from mn_sdk.text_memory import runtime_text_memory, retrieve_memory_context
from .catalog_store import fingerprint
from .graph import QuerySession
from .catalog import LayerUnavailable
from .context_query_plan import VERSION as QUERY_POLICY, plan as graph_plan
from .catalog_sources import publish_inputs as publish_inputs, source_context, hydrate_witnesses
from .catalog_knowledge import publish_runtime_notes as publish_runtime_notes, declare_runtime_schema


def _focus(task, catalog, goal):
    spec = catalog['specs'].get(task.get('aspect_id'), {})
    # Put the current aspect/module first; generic goals must not crowd out task terms.
    return ' '.join(str(x) for x in [task.get('path', ''), task.get('reason', ''),
                     spec.get('title', ''), spec.get('question', ''), task['kind'], goal[:500]] if x)


def graph_context(store, snapshot, task, focus, config, source_evidence=(), request=None):
    modules = snapshot['manifest'].get('modules', {})
    plan = graph_plan(task, focus, modules, source_evidence, config)
    if not plan['modules']:
        return {'status': 'entity_unresolved', 'queries': [], 'incomplete': True,
                'plan': plan, 'unresolved': plan['unresolved'],
                'limitation': 'No module binds to the current source evidence; graph coverage is unknown.'}, []
    requested = [('context_paths', '')] + [(view, name) for name in plan['modules'] for view in plan['views']]
    receipts, witnesses = [], {}
    session = None
    for tool, module in requested:
        key = fingerprint([snapshot['snapshot_id'], QUERY_POLICY, tool, module,
                           *([plan, focus] if tool == 'context_paths' else [])])
        path = f'catalog/graph/{key}.json'
        if store.path(path).exists():
            cached = store.read(path)
        elif len(list(store.path('catalog/graph').glob('*.json'))) >= config['investigation']['max_queries']:
            receipts.append({'tool': tool, 'module': module, 'status': 'budget_exhausted', 'rows': [],
                             'unresolved': ['query_budget_exhausted']})
            continue
        else:
            if session is None:
                session = QuerySession(store.root / 'evidence', config, snapshot['snapshot_id'])
            try:
                if tool == 'context_paths':
                    from .context_traversal import query_paths
                    result = query_paths(session, plan, focus)
                else:
                    result = session.query(tool, module)
            except LayerUnavailable:
                result = {'tool': tool, 'params': {'module': module}, 'status': 'unavailable',
                          'rows': [], 'unresolved': ['layer_unavailable'],
                          'limit_note': 'Required source-backed graph layer is unavailable.'}
            used = session.evidence_ids(result)
            cached = {'query': result, 'evidence': {i: session.evidence[i] for i in used}}
            store.write(path, cached)
        result = json.loads(json.dumps(cached['query'], sort_keys=True))
        # Keep detailed per-file coverage in the durable receipt. Its fixed
        # overhead must not evict source evidence from every small prompt.
        if 'layer_coverage' in result:
            result['layer_coverage'] = {name: {
                'status': value['status'], 'limitation': value.get('limitation', ''),
                'scope_status_counts': dict(Counter(s['status'] for s in value.get('scopes', {}).values()))}
                for name,value in result['layer_coverage'].items()}
        receipts.append({k: result[k] for k in ['tool', 'params', 'status', 'rows', 'result_sha256',
            'limit_note', 'unresolved', 'frontier', 'layer_coverage'] if k in result})
        witnesses.update(sorted(cached['evidence'].items()))
    for witness in witnesses.values():
        source = snapshot['sources'][witness['path']]
        text = ''.join(source['text'].splitlines(keepends=True)[witness['line_start']-1:witness['line_end']])
        if source['sha256'] != witness['sha256'] or text != witness['text']:
            raise ValueError('Graph witness differs from frozen source')
    if request is None:
        # Direct callers must supply the original-corpus binding to hydrate paths.
        source_ids, evidence, hydration_gaps = {}, [], ['source_corpus_unavailable']
    else:
        source_ids, evidence, hydration_gaps = hydrate_witnesses(store, request, snapshot, witnesses)
    unresolved = [*plan['unresolved'], *hydration_gaps]
    for receipt in receipts:
        receipt['rows_omitted'] = 0
        for row in receipt['rows']:
            ids = [eid for key, value in row.items() if key.endswith('evidence_ids')
                   and isinstance(value, list) for eid in value]
            row['source_evidence_ids'] = list(dict.fromkeys(e for eid in ids for e in source_ids.get(eid, [])))
            row['support_complete'] = bool(ids) and all(source_ids.get(eid) for eid in ids)
            if not row['support_complete']:
                unresolved.append('unresolved_source_support')
        unresolved.extend(receipt.get('unresolved', []))
    # Row + full source support admission happens once, against the actual final
    # prompt allowance in review_support. No independent 3,500-byte truncation.
    return {'status': 'incomplete' if unresolved else 'queried', 'queries': receipts,
            'incomplete': bool(unresolved) or any(r.get('status') not in {'ok', 'complete',
                'not_found_in_searched_scope', 'target_found'} for r in receipts),
            'plan': plan, 'unresolved': list(dict.fromkeys(unresolved)),
            'selection_policy': QUERY_POLICY, 'selected_views': plan['views'],
            'limitation': 'Static indexed relationships; bounded search does not establish runtime behavior or absence.'}, evidence


def retrieve(store, saved, snapshot, task, catalog):
    config = saved['request']['retrieval_config']
    focus = _focus(task, catalog, saved['request']['goal'])
    # Direct file scans/lookups and synthesis already carry their complete inputs.
    # Historical navigation is useful only to the open-ended aspect reviewers.
    recall = task['kind'] in {'aspect_analysis', 'aspect_challenge'}
    memory = (runtime_text_memory(config, principal='architecture', scope=saved['request']['memory_scope'])
              if recall else None)
    notes = {'evidence': [], 'incomplete': False, 'status': 'disabled' if recall else 'not_requested'}
    if memory is not None:
        try:
            memory.check()
            declare_runtime_schema(memory,saved['request']['snapshot'])
            settings = config['text_memory']
            path = f"catalog/memory-context/{task['task_id']}.json"
            filters = [{'field':'memory_family','op':'eq','value':'architecture_review'},
                       {'field':'snapshot_id','op':'eq','value':saved['request']['snapshot']}]
            if task.get('aspect_id'):
                filters.append({'field':'aspect_id','op':'eq','value':task['aspect_id']})
            stages = [{'mode':'analytical','consume':'none','analytical':{
                'operation':'recent','timestamp_field':'timestamp',
                'limit':settings['max_results'],'filters':filters}}]
            binding = fingerprint(['context-quality-v1',saved['request']['memory_scope'], snapshot['snapshot_id'], focus, settings, stages])
            if store.path(path).exists():
                cached = store.read(path)
                if cached['binding'] != binding:
                    raise ValueError('Runtime memory replay context changed')
                notes = cached['packet']
            else:
                from mn_sdk.memory_quality import context_requirements
                notes, receipt = retrieve_memory_context(memory, focus, stages=stages,
                    max_results=settings['max_results'], max_context_bytes=settings['max_context_bytes'],
                    hydrate_runtime_records=True,requirements=context_requirements(config,'optional'))
                store.write(path, {'binding': binding, 'packet': notes, 'receipt': receipt})
        finally:
            memory.close()
    if config.get('offline'):
        graph = {'status': 'offline', 'queries': [], 'incomplete': True}
        evidence = []
        originals = {'status':'offline','incomplete':True}
        source_evidence = []
    elif task['kind'] in {'section_synthesis', 'executive_synthesis'}:
        originals, source_evidence = {'status':'not_requested', 'incomplete':False}, []
        graph, evidence = {'status':'not_requested', 'queries':[], 'incomplete':False}, []
    else:
        originals, source_evidence = source_context(store,saved['request'],snapshot,task,focus)
        graph, evidence = graph_context(store, snapshot, task, focus, config, source_evidence, saved['request'])
    context = {'architecture_graph':graph,'source_query':originals}
    if recall:
        context['runtime_memory'] = notes
    return context, list({e['id']: e for e in [*source_evidence, *evidence]}.values())
