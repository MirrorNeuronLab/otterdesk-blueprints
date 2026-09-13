"""Select and capture the repository for this architecture investigation."""
import json
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from .config import validate_config, offline_config
from .events import audit_scope
from .inputs import ingest_source
from .source_input import source_input


def policy(context):
    config = validate_config(context['config'])
    return offline_config(config) if config['offline'] else config


def capture_input(context, *, llm_client=None):
    source = source_input(context['payload'])
    run_dir = Path(context['run_dir'])
    config = policy(context)
    if context['payload'].get('input_folder') and (Path(source) == run_dir.resolve() or Path(source) in run_dir.resolve().parents):
        raise ValueError('Run output must be outside the analyzed input_folder')
    facts = context['payload'].get('graph_export')
    with audit_scope(run_dir):
        manifest = ingest_source(source, run_dir / 'evidence', config, Path(facts) if facts else None)
        (run_dir / 'snapshot.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    path = f"evidence/snapshots/{manifest['id']}"
    refs = [artifact_reference('snapshot', 'snapshot.json'),
            artifact_reference('source_snapshot', path+'/sources.json'),
            artifact_reference('base_graph', path+'/graph.rgx')]
    return {'snapshot': refs[0], 'source_files': manifest['coverage']['source_files'], 'modules': len(manifest['modules'])}, refs
