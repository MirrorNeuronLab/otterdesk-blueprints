"""One isolated review of an immutable admitted request; no owner ledger access."""
import json
import time
from pathlib import Path
from mn_sdk.artifact_handoff import output_directory, register_output, resolve_input
from mn_opencode_skill import OpenCodeRequest, run_opencode
from .opencode_models import provider_config
from .retry_budget import effective_config, effective_deadline
from mn_sdk.run_retry import retry_context


def review_admitted(reference, *, llm_client=None):
    frozen = json.loads(resolve_input(reference).read_text())
    task, request, opener = frozen['task'], frozen['request'], frozen['opencode']
    if retry_context() and 'walltime_seconds' not in frozen:
        raise ValueError('This admitted request predates durable retry allowances. Start a new run.')
    retry_config = effective_config({'opencode': opener, 'catalog_review': {'walltime_seconds': frozen.get('walltime_seconds', 0)}},
        paths={'opencode.timeout_seconds', 'catalog_review.walltime_seconds'})
    opener = retry_config['opencode']
    deadline = effective_deadline(frozen['deadline'], retry_config['catalog_review']['walltime_seconds'])
    value = {'task_id': task['task_id'], 'kind': task['kind'], 'status': 'blocked',
             'reason': 'Review deadline reached before dispatch'}
    expanded = False
    if frozen['offline']:
        value.update(status='not_analyzed', reason='Explicit offline mode: no model call; no architecture conclusion.')
    elif request.get('context_quality',{}).get('action')=='insufficient_evidence':
        value.update(reason='Required source evidence is unavailable.',claims=[],observations=[],
                     limitations=request['context_quality']['reasons'])
    elif time.time() < deadline:
        if llm_client is None:
            if b'openshell-sandbox' not in Path('/proc/1/cmdline').read_bytes():
                raise RuntimeError('Live review requires OpenShell')
            folder = output_directory().parent / 'review-work'
            folder.mkdir(parents=True, exist_ok=True)
            provider = folder / 'provider-config.json'
            provider.write_text(json.dumps(provider_config(opener)))
            invocation = OpenCodeRequest(folder=str(folder), mode='review',
                prompt=request['prompt'], model=opener['model'], sandbox_root='/sandbox/job',
                timeout_seconds=max(1, min(opener['timeout_seconds'], int(deadline-time.time()))),
                max_output_bytes=opener['max_output_bytes'])
        try:
            raw = (run_opencode(invocation, env={'OPENCODE_CONFIG': str(provider)}).text
                   if llm_client is None else llm_client(request['prompt']))
            if not isinstance(raw, str) or len(raw.encode()) > 200000:
                raise ValueError('Response exceeds task quota')
            value = json.loads(raw)
            expanded = True
        except Exception as exc:
            # Model/provider failures are domain outcomes. Input resolution,
            # sandbox setup and artifact publication still fail hard.
            value = {'task_id': task['task_id'], 'kind': task['kind'],
                     'status': 'blocked',
                     'reason': f'{type(exc).__name__}: model review failed or returned invalid JSON.'}
    result = {'task_id': task['task_id'], 'request_hash': frozen['request_hash'],
              'value': value, 'expand_evidence': expanded}
    name = 'review.json'
    (output_directory()/name).write_text(json.dumps(result))
    ref = register_output(name, kind='architecture_review_result')
    return {'task_id': task['task_id'], 'status': 'review_returned', 'result': ref}
