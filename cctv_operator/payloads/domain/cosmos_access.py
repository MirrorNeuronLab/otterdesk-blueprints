"""One active Cosmos request for image understanding and Markdown observation creation."""

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path
import json

from mn_sdk_common.committed_artifacts import CommittedJsonStore
from mn_sdk_common.files import atomic_write_json


def reserve_calls(run_dir, identifier, count, limit, *, now=None):
    """Share the camera's rolling image-call allowance with explicit history review."""
    now = time.time() if now is None else now
    store = CommittedJsonStore(run_dir)
    path = Path(run_dir) / 'cosmos_call_admissions.json'
    with store.locked('cosmos-call-admissions'):
        try:
            rows = json.loads(path.read_text())
        except FileNotFoundError:
            rows = {}
        prior = rows.get(identifier)
        if prior is not None:
            if prior['count'] != count:
                raise ValueError('Cosmos admission changed its image count')
            return True
        rows = {key: row for key, row in rows.items() if now - row['at'] < 60}
        if sum(row['count'] for row in rows.values()) + count > limit:
            return False
        rows[identifier] = {'at': now, 'count': count}
        atomic_write_json(path, rows)
        return True


@contextmanager
def cosmos_slot(run_dir, *, timeout=120):
    path = Path(run_dir) / "cosmos.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    with path.open("a+b") as handle:
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Cosmos is still processing earlier video")
                time.sleep(.1)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
