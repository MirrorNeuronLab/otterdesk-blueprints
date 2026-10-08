"""One active Cosmos request for image understanding and Markdown observation creation."""

import fcntl
import time
from contextlib import contextmanager
from pathlib import Path


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
