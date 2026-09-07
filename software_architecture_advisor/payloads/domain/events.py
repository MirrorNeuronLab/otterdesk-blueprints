"""Architecture action audit within an SDK-owned run; no workflow lifecycle."""
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
import json
from pathlib import Path
import time
from types import SimpleNamespace

_active = ContextVar('architecture_audit', default=None)


def current_run():
    return _active.get()


def emit(event, **details):
    audit = current_run()
    if audit is None:
        return
    audit.sequence += 1
    entry = {"timestamp": datetime.now(timezone.utc).isoformat(), "sequence": audit.sequence,
             "elapsed_ms": round((time.monotonic()-audit.started)*1000, 3),
             "run_id": audit.id, **audit.context, "event": event, **details}
    with (audit.directory / 'events.log').open('a', encoding='utf-8') as output:
        output.write(json.dumps(entry, separators=(',', ':'))+'\n')


def event_context(**details):
    audit = current_run()
    if audit:
        for key, value in details.items():
            if value is None:
                audit.context.pop(key, None)
            else:
                audit.context[key] = value


def intent_created(goal):
    if current_run():
        emit('intent.created', goal=goal)


@contextmanager
def audit_scope(directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / 'events.log'
    sequence = 0
    if path.exists():
        with path.open(encoding='utf-8') as log:
            for line in log:
                sequence = json.loads(line)['sequence']
    token = _active.set(SimpleNamespace(id=directory.name, directory=directory,
        sequence=sequence, started=time.monotonic(), context={}))
    try:
        yield
    finally:
        _active.reset(token)
