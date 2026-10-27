"""Job-scoped candidate checkpoints; every reuse is revalidated, never approval."""
from hashlib import sha256
import json

from mn_sdk.blueprint_support import write_json
from .document_policy import policy_identity


def identity(packet):
    # This version binds requirement semantics and evidence admission, not the
    # model's wire format. Old literal-quote candidates require the same checks.
    context = {key: packet.get(key) for key in ('line_context', 'preceding_context', 'preceding_context_complete')}
    return {'policy': policy_identity(), 'context_sha256': sha256(json.dumps(context, sort_keys=True).encode()).hexdigest(), **{key: packet[key] for key in
            ('snapshot_id', 'path', 'sha256', 'start_line', 'end_line')}}


def location(block, packet):
    root = block.job_directory / 'cache/code-verifier/extraction'
    key = sha256(json.dumps(identity(packet), sort_keys=True).encode()).hexdigest()
    return root / f'{key}.json'


def load(block, packet, validate):
    path = location(block, packet)
    if not path.is_file():
        return None
    if path.is_symlink() or path.stat().st_size > 1_000_000:
        raise ValueError('Invalid extraction checkpoint file.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or not isinstance(value.get('response'), dict):
        raise ValueError('Invalid extraction checkpoint structure.')
    if value['response'].get('extraction_gaps'):
        raise ValueError('Incomplete source coverage cannot be a reusable checkpoint.')
    if value.get('identity') != identity(packet) or value.get('job_scope') != block.job_directory.name:
        raise ValueError('Extraction checkpoint does not match this job and source.')
    validate(value['response'])
    return value


def store(block, packet, response, validate):
    validate(response)
    if response.get('extraction_gaps'):
        return
    path = location(block, packet)
    value = {'identity': identity(packet), 'job_scope': block.job_directory.name,
             'producer_execution_id': block.job_id,
             'producer_run_id': block.run_id, 'response': response}
    if len(json.dumps(value).encode()) > 1_000_000:
        return  # Run artifacts remain authoritative; caching is only an optimization.
    path.parent.mkdir(parents=True, exist_ok=True)
    files = list(path.parent.glob('*.json'))
    if not path.exists() and len(files) >= 2048:
        min(files, key=lambda item: item.stat().st_mtime).unlink()
    write_json(path, value)
