"""Owner-only task admission and reconciliation of Core-committed reviews."""
import json
from mn_sdk.artifact_handoff import publish_input, resolve_committed, store_root
from .catalog_store import fingerprint
from .catalog_contract import load_catalog, load_snapshot
from .review_packets import chunk_snapshot
from .review_prompts import build_prompt, expand_evidence
from .review_response import validate_result


def admit(store, saved, plan, task, review, opener, *, run_id):
    """Freeze prompt before reserving; reserve before returning dispatch inputs."""
    task_id = task['task_id']
    identity = fingerprint({'task': task, 'settings': saved['request']})
    request_path = f'catalog/requests/{task_id}.json'
    if store.path(request_path).exists():
        request = store.read(request_path)
        if request['identity'] != identity:
            raise ValueError('Inconsistent admission replay')
    else:
        snapshot = load_snapshot(store.root)
        packets = {p['packet_id']: p for p in chunk_snapshot(snapshot, review['chunk_bytes'])}
        from .catalog_retrieval import retrieve
        catalog = load_catalog()
        retrieval, graph_evidence = retrieve(store, saved, snapshot, task, catalog)
        request = {'identity': identity, **build_prompt(task, catalog, snapshot, packets,
            store.results(), review['prompt_bytes'], plan['omitted'],
            retrieval=retrieval, graph_evidence=graph_evidence)}
        store.write(request_path, request)
    request_hash = fingerprint(request)
    # Existing reservations are retained, including unknown executions. Core's
    # transaction guards dispatch replay; admission never refunds a reservation.
    if not review['offline'] and store.reserve(task_id, request_hash, review['max_calls']) == 'exhausted':
        return None
    frozen = {'task': task, 'request': request, 'request_hash': request_hash,
              'opencode': opener, 'offline': review['offline'], 'deadline': saved['deadline']}
    ref = publish_input(frozen, run_id=run_id, kind='architecture_review_input')
    store.write(f'catalog/admissions/{task_id}.json', {'input': ref, 'runtime_run_id': run_id})
    return ref


def reconcile(store):
    """Record domain receipts only from verified Core commits, idempotently."""
    pending = {}
    runs = set()
    for admission_path in sorted(store.path('catalog/admissions').glob('*.json')):
        task_id = admission_path.stem
        if store.result(task_id) is not None:
            continue
        admission = store.read(str(admission_path.relative_to(store.root)))
        pending[task_id] = admission
        runs.add(admission['runtime_run_id'])
    candidates = {}
    for run_id in runs:
        for receipt_path in sorted((store_root(run_id) / 'commits').glob('*/receipt.json')):
            receipt = json.loads(receipt_path.read_text())
            if receipt['execution']['exit_code'] != 0:
                continue
            task_id = receipt['execution'].get('structured_result', {}).get('outputs', {}).get('task_id')
            if task_id not in pending:
                continue
            for ref in receipt['references']:
                if ref['kind'] == 'architecture_review_result':
                    candidate = json.loads(resolve_committed(ref, run_id=run_id).read_text())
                    if candidate.get('task_id') != task_id:
                        raise ValueError('Committed review task identity differs')
                    if task_id in candidates and candidates[task_id][0] != ref:
                        raise ValueError('Conflicting task commits')
                    candidates[task_id] = (ref, candidate)
    for task_id, (ref, candidate) in candidates.items():
        admission = pending[task_id]
        frozen = json.loads(resolve_committed(admission['input'], run_id=admission['runtime_run_id']).read_text())
        if candidate['request_hash'] != frozen['request_hash']:
            raise ValueError('Committed review request identity differs')
        request, task = frozen['request'], frozen['task']
        value = candidate['value']
        snapshot = load_snapshot(store.root)
        # Packet keys validate follow-up proposals; citation bytes come
        # from the frozen owner snapshot, never sandbox ledger copies.
        saved = store.read('catalog/context.json')
        packets = {p['packet_id']: p for p in chunk_snapshot(snapshot, saved['request']['review']['chunk_bytes'])}
        try:
            if candidate.get('expand_evidence'):
                value = expand_evidence(value, request['evidence'])
            value = validate_result({**task, 'input_task_ids': request['input_task_ids']}, value,
                snapshot, packets, request['requirements'], list(request['evidence'].values()))
        except (ValueError, TypeError, KeyError, AttributeError) as exc:
            # Verified transport does not make untrusted model claims valid.
            # Preserve the failed task without admitting any of its claims.
            value = {'task_id': task['task_id'], 'kind': task['kind'], 'status': 'blocked',
                     'reason': f'{type(exc).__name__}: structured evidence validation failed.',
                     'claims': [], 'observations': [], 'proposed_followups': []}
        value.update(identity=request['identity'], request_hash=frozen['request_hash'],
                     model=frozen['opencode']['model'], input_omissions=request['omissions'],
                     input_task_ids=request['input_task_ids'], artifact_commit=ref)
        if value.get('coverage') == 'complete_for_stated_scope' and any(
            request['omissions'][k] for k in ['source_packets', 'prior_results', 'evidence_spans']):
            value['coverage'] = 'partial'
        store.finish(task_id, value)
