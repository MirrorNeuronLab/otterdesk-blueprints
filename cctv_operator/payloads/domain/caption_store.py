"""Job-owned caption journal, command receipts and crash-cleanup ownership."""

import json
from pathlib import Path
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from .errors import CameraStateError


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    if not isinstance(value, str) or len(value) > 64:
        raise ValueError("A caption needs a timestamp with timezone.")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("A caption needs a timestamp with timezone.")
    return result.astimezone(timezone.utc).isoformat()


class CaptionStore:
    def __init__(self, path, *, job_id, run_id, source_id, max_records=10000):
        self.path, self.job_id, self.run_id, self.source_id = Path(path), job_id, run_id, source_id
        self.max_records = max_records
        if isinstance(max_records, bool) or not isinstance(max_records, int) or not 1 <= max_records <= 100000:
            raise CameraStateError("Couldn't configure caption retention. Choose a capacity from 1 to 100,000.")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS identity (job_id TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS captions (
                    revision INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                    run_id TEXT NOT NULL, source_id TEXT NOT NULL,
                    start_time TEXT NOT NULL, end_time TEXT NOT NULL,
                    payload TEXT NOT NULL, published INTEGER NOT NULL DEFAULT 0);
                CREATE TABLE IF NOT EXISTS state (key TEXT PRIMARY KEY, payload TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS commands (
                    id TEXT PRIMARY KEY, request TEXT NOT NULL, receipt TEXT NOT NULL);
            """)
            identities = [row[0] for row in db.execute("SELECT job_id FROM identity")]
            if identities and identities != [job_id]:
                raise ValueError("Caption storage belongs to another Job.")
            db.execute("INSERT OR IGNORE INTO identity VALUES (?)", (job_id,))

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def state(self, key):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM state WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else None

    def set_state(self, key, value):
        with self.connect() as db:
            if value is None:
                db.execute("DELETE FROM state WHERE key=?", (key,))
            else:
                db.execute("INSERT OR REPLACE INTO state VALUES (?,?)", (key, json.dumps(value)))

    def append(self, caption):
        payload = json.dumps(caption, sort_keys=True)
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM captions WHERE id=?", (caption["id"],)).fetchone()
            if row:
                previous, incoming = json.loads(row[0]), dict(caption)
                previous.pop("received_at", None)
                incoming.pop("received_at", None)
                if previous != incoming:
                    raise ValueError("A caption identity was reused with different content.")
                return False
            if db.execute("SELECT count(*) FROM captions").fetchone()[0] >= self.max_records:
                raise CameraStateError("Caption storage is full. Export and review retention before starting another run.")
            db.execute("INSERT INTO captions(id,run_id,source_id,start_time,end_time,payload) VALUES (?,?,?,?,?,?)", (
                caption["id"], self.run_id, self.source_id, caption["start_time"], caption["end_time"], payload,
            ))
        return True

    def history(self, *, after="", before="", current_run=False, limit=300):
        terms, values = ["source_id=?"], [self.source_id]
        if current_run:
            terms.append("run_id=?")
            values.append(self.run_id)
        for supplied, operator, column in ((after, ">=", "end_time"), (before, "<=", "start_time")):
            if supplied:
                terms.append(f"{column}{operator}?")
                values.append(timestamp(supplied))
        if after and before and timestamp(after) > timestamp(before):
            raise ValueError("The history interval ends before it starts.")
        limit = min(max(int(limit), 1), 300)
        with self.connect() as db:
            count = db.execute("SELECT count(*) FROM captions WHERE " + " AND ".join(terms), values).fetchone()[0]
            rows = db.execute("SELECT revision,payload FROM captions WHERE " + " AND ".join(terms)
                              + " ORDER BY start_time DESC,revision DESC LIMIT ?", [*values, limit]).fetchall()
        return {"observations": [json.loads(row["payload"]) | {"revision": row["revision"]} for row in reversed(rows)],
                "omitted_count": max(0, count - len(rows)), "total_count": count}

    def pending(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM captions WHERE published=0 AND source_id=? AND run_id=? ORDER BY revision LIMIT 300",
                              (self.source_id, self.run_id)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def saved(self, identity):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM captions WHERE id=? AND source_id=? AND run_id=?",
                             (identity, self.source_id, self.run_id)).fetchone()
        return json.loads(row[0]) if row else None

    def published(self, identity):
        with self.connect() as db:
            db.execute("UPDATE captions SET published=1 WHERE id=?", (identity,))

    def command(self, identity, request=None, receipt=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT request,receipt FROM commands WHERE id=?", (identity,)).fetchone()
            encoded = json.dumps(request, sort_keys=True) if request is not None else None
            if row and encoded is not None and row["request"] != encoded:
                raise ValueError("This request ID already belongs to another monitoring change.")
            if receipt is not None:
                db.execute("INSERT OR REPLACE INTO commands VALUES (?,?,?)",
                           (identity, encoded if encoded is not None else row["request"], json.dumps(receipt)))
                return receipt
        return json.loads(row["receipt"]) if row else None
