"""Select and capture the repository for this architecture investigation."""

from mn_sdk.agent_events import activity_operation
from mn_sdk_common.files import atomic_write_json
import json
from pathlib import Path
from .catalog_contract import load_snapshot
from .config import validate_config, offline_config
from .events import audit_scope
from .inputs import ingest_source
from .source_input import source_input
from .state import request_inputs, freeze_files, save_state


def policy(block):
    config = validate_config(block.original_config)
    return offline_config(config) if config['offline'] else config


@activity_operation('Examining repository inputs', completed='Examining repository inputs: completed')
def capture_input(block, inputs):
    block.check()
    request = request_inputs(block, inputs)
    source = source_input(request)
    run_dir = block.store.run_dir
    config = policy(block)
    if request.get('input_folder') and (Path(source) == run_dir or Path(source) in run_dir.parents):
        raise ValueError('Run output must be outside the analyzed input_folder')
    facts = request.get('graph_export')
    block.store.commit('capture-request.json', {
        'version': 'architecture.capture_request/v1', 'source': str(source),
        'graph_export': str(facts) if facts else None, 'config': config,
    })
    with audit_scope(run_dir):
        if (run_dir / 'snapshot.json').exists():
            manifest = load_snapshot(run_dir)['manifest']
        else:
            manifest = ingest_source(source, run_dir / 'evidence', config, Path(facts) if facts else None)
            atomic_write_json(run_dir / 'snapshot.json', manifest)
    path = f"evidence/snapshots/{manifest['id']}"
    files = freeze_files(block, ['snapshot.json', *[str(file.relative_to(run_dir))
        for file in (run_dir/path).iterdir() if file.is_file()]])
    if request.get('review_file'):
        original = Path(request['review_file'])
        if original.is_symlink() or not original.is_file() or original.stat().st_size > 2*1024*1024:
            raise ValueError('Review import must be a bounded regular JSON file')
        encoded = original.read_bytes()
        json.loads(encoded)
        saved = block.store.commit_bytes('architecture/review-import.json', encoded, kind='architecture_review_import')
        request['review_file'] = str(block.store.path(saved.path))
        files[saved.path] = saved.to_dict()
    block.check()
    return {'snapshot': files['snapshot.json'], 'source_files': manifest['coverage']['source_files'],
        'modules': len(manifest['modules']), 'evidence': save_state(block, 'capture', inputs=request, files=files)}
