"""Job-owned immutable camera assets and the locator catalog for Membrane sources."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3

from mn_context_engine_sdk import MediaReference
from mn_sdk.context_session.contracts import digest
from mn_sdk_common.files import atomic_write_bytes

from .video_summary import _time


class CameraHistoryStore:
    def __init__(self, job_directory, *, job_id, camera_id, source_key):
        directory = Path(job_directory)
        if not directory.is_absolute() or directory.name != job_id:
            raise ValueError('Camera history requires the Core-provided Job data directory')
        self.identity = {'job_id': job_id, 'camera_id': camera_id, 'source_key': source_key}
        self.key = digest(self.identity)
        self.root = directory / 'state' / 'camera_history' / self.key
        if not self.root.resolve().is_relative_to(directory.resolve()):
            raise ValueError('Camera history state must remain inside the Job directory')
        self.root.mkdir(parents=True, exist_ok=True)
        catalog = self.root / 'catalog.sqlite3'
        if catalog.is_symlink():
            raise ValueError('Camera history catalog must be an original Job file')
        self.db = sqlite3.connect(catalog, timeout=30)
        catalog.chmod(0o600)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('CREATE TABLE IF NOT EXISTS identity(value TEXT NOT NULL)')
        value = json.dumps(self.identity, sort_keys=True)
        with self.db:
            prior = self.db.execute('SELECT value FROM identity').fetchone()
            if prior and prior[0] != value:
                raise ValueError('Camera history belongs to a different Job, camera or source')
            if not prior:
                self.db.execute('INSERT INTO identity VALUES (?)', (value,))
            self.db.execute('''CREATE TABLE IF NOT EXISTS observations(
                id TEXT PRIMARY KEY, run_id TEXT NOT NULL, captured REAL NOT NULL, began REAL NOT NULL,
                entry TEXT NOT NULL, model_identity TEXT)''')
            self.db.execute('CREATE INDEX IF NOT EXISTS by_capture ON observations(captured,id)')

    def _uri(self, sha256):
        return f'artifact://cctv-history/{self.key}/{sha256}.jpg'

    def put_image(self, data, expected_hash):
        reference = MediaReference.from_bytes(data, uri=self._uri(hashlib.sha256(data).hexdigest()), mime_type='image/jpeg')
        if reference.sha256 != expected_hash:
            raise ValueError('Camera history image differs from its admitted frame hash')
        path = self.root / 'images' / (reference.sha256 + '.jpg')
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Camera history image must be an original regular asset')
        if path.exists():
            self.load_image(reference)
        else:
            atomic_write_bytes(path, data, create_parents=True)
            directory = os.open(path.parent, os.O_RDONLY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        return reference

    def load_image(self, reference):
        if reference.uri != self._uri(reference.sha256) or reference.mime_type != 'image/jpeg':
            raise ValueError('Camera image reference is outside this Job/camera/source')
        path = self.root / 'images' / (reference.sha256 + '.jpg')
        if path.is_symlink() or path.parent.is_symlink():
            raise ValueError('Camera history image must be an original regular asset')
        data = path.read_bytes()
        reference.verify(data)
        return data

    def stage(self, entry):
        encoded = json.dumps(entry, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with self.db:
            prior = self.db.execute('SELECT entry FROM observations WHERE id=?', (entry['id'],)).fetchone()
            if prior and prior[0] != encoded:
                raise ValueError('Immutable camera history observation changed')
            self.db.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,NULL)',
                (entry['id'], entry['run_id'], _time(entry['capture_ended_at']).timestamp(),
                 _time(entry['capture_started_at']).timestamp(), encoded))

    def indexed(self, identifier, identity):
        with self.db:
            self.db.execute('UPDATE observations SET model_identity=? WHERE id=?',
                (json.dumps(identity), identifier))

    def entries(self, *, after='', before='', run_id=None):
        predicates, args = [], []
        for bound, field, op in ((after, 'captured', '>='), (before, 'began', '<=')):
            if bound:
                predicates.append(field + ' ' + op + ' ?')
                args.append(_time(bound).timestamp())
        if after and before and _time(after) > _time(before):
            raise ValueError('history after must precede before')
        if run_id:
            predicates.append('run_id=?')
            args.append(run_id)
        where = ' WHERE ' + ' AND '.join(predicates) if predicates else ''
        # The native explicit source scope is bounded to 5,000 identities. A
        # larger interval is rejected by the caller, never silently made recent.
        rows = self.db.execute('SELECT entry,model_identity FROM observations' + where +
            ' ORDER BY captured DESC,id LIMIT 5001', args).fetchall()
        return [(json.loads(entry), json.loads(identity) if identity else None) for entry, identity in rows]

    def close(self):
        self.db.close()
