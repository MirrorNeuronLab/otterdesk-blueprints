"""Investigate the captured architecture with one globally bounded model session."""
import json
from pathlib import Path
from mn_sdk.llm import LLMClient
from mn_sdk.step_runtime import artifact_reference
from .events import audit_scope
from .intake import policy
from .investigator import investigate
from .model import JsonModel


def investigate_repository(context, *, llm_client=None):
    run_dir = Path(context['run_dir'])
    snapshot = json.loads((run_dir / 'snapshot.json').read_text())
    config = policy(context)
    model = None
    if not config['offline']:
        client = llm_client or LLMClient.from_env(strict=True)
        config['llm']['model'] = client.model
        model = JsonModel(config, client=client)
    with audit_scope(run_dir):
        result = investigate(run_dir / 'evidence', config, context['payload']['goal'],
                             offline=config['offline'], model=model, snapshot_id=snapshot['id'])
    if result['status'] == 'failed':
        raise RuntimeError('Architecture investigation failed; inspect investigation.json, model-trace.json and events.log')
    refs = [artifact_reference('investigation', 'investigation.json'),
            artifact_reference('model_trace', 'model-trace.json'),
            artifact_reference('events', 'events.log')]
    return {'investigation': refs[0], 'status': result['status'], 'findings': len(result['findings']),
            'queries': result['metrics']['queries']}, refs
