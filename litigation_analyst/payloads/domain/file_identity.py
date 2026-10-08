"""Case-owned persistent identity ledger over frozen original file bytes."""
import fcntl
import json
import os
from pathlib import Path
from uuid import uuid4

from mn_graph_analysis_skill import (FileIdentityRegistry, compute_content_hash,
    get_repository_identity, git_rename_hints)


def capture_file_identities(source, run_dir, context, hashes):
    settings = context['config']['investigation']
    explicit = settings.get('repository_id')
    job = context.get('job_id') or os.environ.get('MN_JOB_ID')
    # Case/matter scope is supplied by the trusted owner, never an absolute path.
    scope = explicit or ("case:" + job if job else "case-scope:" + settings['access_scope'])
    ledger = Path(run_dir).parent / 'file-identities' / (compute_content_hash(scope.encode()) + '.json')
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.with_suffix('.lock').open('a') as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        previous = json.loads(ledger.read_text()) if ledger.exists() else None
        repository_id = get_repository_identity(source, repository_id=explicit or ("case:" + job if job else None),
            previous_id=previous['registry']['repository_id'] if previous else None)
        prior = previous['registry'] if previous and previous['registry']['repository_id'] == repository_id else None
        registry = FileIdentityRegistry(repository_id, prior)
        identities = registry.reconcile({p.relative_to(source).as_posix(): h for p, h in hashes.items()},
            renames=git_rename_hints(source, previous.get('git_anchor') if prior else None))
        from subprocess import run, SubprocessError
        anchor = None
        try:
            anchor = run(['git', '-C', str(source), '-c', f'safe.directory={source}', 'rev-parse', 'HEAD'],
                capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        except (OSError, SubprocessError):
            pass
        value = {'registry': registry.export(), 'git_anchor': anchor}
        temporary = ledger.with_name(ledger.name + '.' + uuid4().hex + '.tmp')
        temporary.write_text(json.dumps(value, sort_keys=True))
        temporary.replace(ledger)
    return repository_id, identities
