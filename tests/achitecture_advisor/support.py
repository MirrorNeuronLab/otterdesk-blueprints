"""Fixtures exercise the converted domain inside an SDK-shaped artifact boundary."""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / 'achitecture_advisor'
RGX = Path(os.environ.get('ADVISOR_RGX_BINARY', '/not-installed/rgx'))


def configuration():
    from domain.config import validate_config, offline_config
    cfg = validate_config(json.loads((ROOT / 'config/default.json').read_text()))
    cfg = offline_config(cfg)
    cfg['graph']['binary'] = str(RGX)
    return cfg


def audited_investigate(workspace, config, goal, **kwargs):
    from domain.events import audit_scope
    from domain.investigator import investigate
    from domain.reporting import publish_review
    workspace = Path(workspace)
    snapshot = kwargs.get('snapshot_id') or (workspace / 'CURRENT').read_text().strip()
    run_dir = workspace.parent / ('review-' + workspace.name)
    run_dir.mkdir(exist_ok=True)
    (run_dir / 'snapshot.json').write_bytes((workspace / 'snapshots' / snapshot / 'manifest.json').read_bytes())
    evidence = run_dir / 'evidence'
    if not evidence.exists():
        evidence.symlink_to(workspace, target_is_directory=True)
    with audit_scope(run_dir):
        result = investigate(workspace, config, goal, **kwargs)
    if result['status'] != 'failed':
        publish_review({'run_dir': run_dir})
    return result
