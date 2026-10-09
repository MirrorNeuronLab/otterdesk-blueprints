"""Append-only Job snapshots with atomic publication and explicit offline review import."""
from contextlib import contextmanager
from copy import deepcopy
import fcntl
import json
import os
import re
from pathlib import Path
import shutil
import tempfile
from datetime import datetime

from .catalog_store import fingerprint
from .workspace_projection import compare

ACTIONS = {'Accept with qualification', 'Revise', 'Request evidence', 'Dismiss', 'Reopen'}


def atomic(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError('Workspace output must not be a link')
    fd, name = tempfile.mkstemp(prefix='.publish-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(body)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False, indent=2).encode('utf-8')


@contextmanager
def storage(context):
    job_id, job_root = context.get('job_id'), context.get('job_data_dir')
    if bool(job_id) != bool(job_root):
        raise ValueError('Persistent architecture history requires both Job identity and Job data directory')
    root = Path(job_root) / 'architecture_results' if job_id else Path(context['run_dir']) / 'architecture_results'
    if root.is_symlink():
        raise ValueError('Architecture storage must not be a link')
    root.mkdir(parents=True, exist_ok=True)
    with (root / 'publication.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        marker = root / 'owner.json'
        owner = {'job_id': job_id or None, 'schema': 'mn.architecture.job_results.v1'}
        if marker.exists() and json.loads(marker.read_text()) != owner:
            raise ValueError('Architecture results belong to a different Job')
        atomic(marker, json_bytes(owner))
        yield root, 'Job history' if job_id else 'Single run; Job history unavailable'


def apply_reviews(workspace, source):
    if not isinstance(source, dict) or source.get('schema_version') != 'mn.architecture.reviews.v1' or source.get('repository_id') != workspace['repository_id']:
        raise ValueError('Review import has wrong schema or repository identity')
    rows = source.get('decisions')
    if not isinstance(rows, list) or len(rows) > 500:
        raise ValueError('Review import requires at most 500 decisions')
    findings = {f['continuity_key']: f for f in workspace['findings']}
    for row in rows:
        if not isinstance(row, dict) or row.get('action') not in ACTIONS or any(
            not isinstance(row.get(k), str) or not row[k].strip() or len(row[k]) > 4000
            for k in ('id', 'continuity_key', 'material_digest', 'actor', 'at', 'rationale')):
            raise ValueError('Review import requires actor, time, rationale and exact material identity')
        if datetime.fromisoformat(row['at'].replace('Z', '+00:00')).tzinfo is None:
            raise ValueError('Review time must include timezone')
        finding = findings.get(row['continuity_key'])
        if not finding:
            continue
        prior = next((r for r in finding['review_history'] if r['id'] == row['id']), None)
        if prior and prior != row:
            raise ValueError('Immutable review changed')
        if row not in finding['review_history']:
            finding['review_history'].append(deepcopy(row))
        matching = [r for r in finding['review_history'] if r['material_digest'] == finding['material_digest']]
        if matching:
            finding['review_state'] = matching[-1]['action']
            by_actor = {r['actor']: r['action'] for r in matching}
            if len(set(by_actor.values())) > 1:
                finding['review_state'] = 'Reviewers disagree'
        else:
            finding['review_state'] = 'Needs reassessment'


def retain(context, workspace):
    workspace = deepcopy(workspace)
    run = Path(context['run_dir'])
    with storage(context) as (root, mode):
        data = root / 'data'
        index_path = data / 'index.json'
        index = json.loads(index_path.read_text()) if index_path.exists() else {
            'schema_version': 'mn.architecture.history.v1', 'snapshots': [], 'latest': None}
        if index.get('schema_version') != 'mn.architecture.history.v1':
            raise ValueError('Unsupported architecture history schema')
        if any(not re.fullmatch(r'snapshot-[0-9a-f]{24}', str(r.get('id', ''))) for r in index['snapshots']):
            raise ValueError('Invalid retained snapshot identity')
        identity = workspace['id']
        record = next((r for r in index['snapshots'] if r['id'] == identity), None)
        directory = data / 'snapshots' / identity
        review_file = context.get('payload', {}).get('review_file')
        review_source = None
        if review_file:
            path = Path(review_file)
            if path.is_symlink() or not path.is_file() or path.stat().st_size > 2*1024*1024:
                raise ValueError('Review import must be a bounded regular JSON file')
            review_source = json.loads(path.read_text(encoding='utf-8'))
            workspace['review_input_digest'] = fingerprint(review_source)
        original = fingerprint(workspace)
        if record:
            saved = json.loads((directory / 'workspace.json').read_text())
            if record['sha256'] != fingerprint(saved) or saved['input_digest'] != original:
                raise ValueError('Architecture snapshot changed on replay')
            workspace = saved
        else:
            previous = next((r for r in reversed(index['snapshots']) if r['repository_id'] == workspace['repository_id']), None)
            old = json.loads((data / 'snapshots' / previous['id'] / 'workspace.json').read_text()) if previous else None
            if old is not None and fingerprint(old) != previous['sha256']:
                raise ValueError('Prior architecture snapshot integrity mismatch')
            workspace['changes'] = compare(workspace, old)
            for finding in workspace['findings']:
                finding.setdefault('revision', 1)
            workspace['history_mode'] = mode
            workspace['input_digest'] = original
            if review_source is not None:
                apply_reviews(workspace, review_source)
            directory.mkdir(parents=True, exist_ok=True)
            # Exact delivery replay can complete an interrupted directory without rewriting history.
            body = json_bytes(workspace)
            existing = directory / 'workspace.json'
            if existing.exists() and existing.read_bytes() != body:
                raise ValueError('Uncommitted architecture publication changed')
            atomic(existing, body)
            for name in ['report.md', 'report.json', 'sections', 'work_packages', 'evidence.json',
                         'claims.json', 'findings.json', 'recommendations.json', 'assumptions.json',
                         'verification_tasks.json', 'coverage.json', 'work_packages.json', 'roadmap.json',
                         'improvement_prompts.md', 'improvement_prompts.json']:
                source = run / name
                if source.is_dir():
                    shutil.copytree(source, directory / name, dirs_exist_ok=True)
                elif source.is_file():
                    atomic(directory / name, source.read_bytes())
            record = {'id': identity, 'snapshot_id': workspace['snapshot_id'], 'run_id': workspace['run_id'],
                'repository_id': workspace['repository_id'], 'captured_at': workspace['captured_at'],
                'revision': workspace['revision'], 'status': workspace['status'], 'sha256': fingerprint(workspace),
                'files': len(workspace['files']), 'findings': len(workspace['findings'])}
            index['snapshots'].append(record)
            index['latest'] = identity
            atomic(index_path, json_bytes(index))
        # Only a mutable latest pointer is replaced. All immutable snapshot records remain.
        latest = json.loads((data / 'snapshots' / index['latest'] / 'workspace.json').read_text())
        atomic(data / 'workspace.json', json_bytes(latest))
        # Stage declared job_files under the shared output tree. SDK owns host delivery.
        shutil.copytree(data, run / 'data', dirs_exist_ok=True)
        return workspace, index, root
