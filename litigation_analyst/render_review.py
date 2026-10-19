"""Create a separate reading copy of a completed frozen workspace, without inference."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / 'payloads'))


def render_copy(run, output):
    from domain.workspace_review import attach
    from domain.workspace_web import render

    run, output = Path(run).resolve(), Path(output).resolve()
    if output == run or output in run.parents or run in output.parents:
        raise ValueError('Choose a separate destination outside the frozen run')
    workspace_path = run / 'case/workspace.json'
    workspace = attach(deepcopy(json.loads(workspace_path.read_text(encoding='utf-8'))))
    workspace['reading_copy'] = {'source_snapshot': workspace['snapshot_id'],
        'workspace_sha256': hashlib.sha256(workspace_path.read_bytes()).hexdigest(),
        'definition': 'Supplemental reading copy. Original report, findings and audit artifacts are unchanged. No model analysis or attorney review performed.'}
    page = render(workspace)
    if len(page.encode()) > 32 * 1024 * 1024:
        raise ValueError('Reading copy exceeds 32 MiB')
    # Never merge this confidential projection into an older, broader copy.
    output.mkdir(parents=True, exist_ok=False)
    originals = output / 'originals'
    originals.mkdir()
    try:
        for source in workspace['sources']:
            if not source['original_included']:
                continue
            digest = source['original_sha256']
            if len(digest) != 64 or any(c not in '0123456789abcdef' for c in digest):
                raise ValueError('Invalid original source digest')
            original = run / 'case/originals' / digest
            if original.is_symlink() or hashlib.sha256(original.read_bytes()).hexdigest() != digest:
                raise ValueError('Original source integrity check failed')
            shutil.copyfile(original, originals / (digest + ('.pdf' if source['media_type'] == 'application/pdf' else '.bin')))
        for report in workspace['reading_reports']:
            (output / report['filename']).write_text(report['markdown'], encoding='utf-8')
        (output / 'review-data.json').write_text(json.dumps(workspace, ensure_ascii=False, indent=2), encoding='utf-8')
        (output / 'index.html').write_text(page, encoding='utf-8')
    except Exception:
        shutil.rmtree(output)
        raise
    return output / 'index.html'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path, help='Completed run containing case/workspace.json')
    parser.add_argument('--output', type=Path, required=True, help='New separate reading-copy directory')
    args = parser.parse_args()
    print(render_copy(args.run, args.output))
