"""Select and capture the repository for this architecture investigation."""
import json
from pathlib import Path
from mn_sdk.step_runtime import artifact_reference
from .config import validate_config, offline_config
from .events import audit_scope
from .inputs import github_url, ingest_source


def source_input(payload):
    folder, url = payload.get('input_folder'), payload.get('repository_url')
    if (folder is None) == (url is None):
        raise ValueError('Specify exactly one of input_folder or repository_url')
    if url is not None:
        if not isinstance(url, str) or len(url) > 2000:
            raise ValueError('repository_url must be an HTTPS GitHub repository URL')
        return github_url(url)
    if not isinstance(folder, str) or not folder.strip() or '://' in folder or folder.startswith('git@'):
        raise ValueError('input_folder must be a local directory path')
    path = Path(folder).expanduser().resolve(strict=True)
    if not path.is_dir():
        raise ValueError('input_folder must be a directory')
    return str(path)


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
