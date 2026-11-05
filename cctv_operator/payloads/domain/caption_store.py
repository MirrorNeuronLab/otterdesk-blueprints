"""Job-owned caption journal, command receipts and crash-cleanup ownership."""

import hashlib
import json
from pathlib import Path
import sqlite3
import time
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
                CREATE TABLE IF NOT EXISTS snapshots (caption_id TEXT PRIMARY KEY, jpeg BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS history_index (
                    caption_id TEXT PRIMARY KEY, model TEXT NOT NULL, sources TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS index_retries (caption_id TEXT PRIMARY KEY, retry_after REAL NOT NULL);
                CREATE INDEX IF NOT EXISTS by_camera_time ON captions(source_id,start_time,revision);
                CREATE INDEX IF NOT EXISTS by_goal_match ON captions(source_id,run_id,
                    json_extract(payload,'$.instruction_revision'),start_time,revision)
                    WHERE json_extract(payload,'$.goal_match')='matched';
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

    def append(self, caption, jpeg=None):
        snapshot = caption.get("snapshot")
        if snapshot or jpeg is not None:
            if (not snapshot or not isinstance(jpeg, bytes) or not 4 <= len(jpeg) <= 512 * 1024
                    or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9")
                    or snapshot["sha256"] != hashlib.sha256(jpeg).hexdigest()
                    or not timestamp(caption["start_time"]) <= timestamp(snapshot["received_at"]) <= timestamp(caption["end_time"])):
                raise ValueError("The snapshot must be the original JPEG received inside this window.")
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
            if jpeg is not None:
                db.execute("INSERT INTO snapshots VALUES (?,?)", (caption["id"], jpeg))
        return True

    def history(self, *, after="", before="", current_run=False, limit=300, goal_revision=None, older_than=None):
        terms, values = ["source_id=?"], [self.source_id]
        if current_run:
            terms.append("run_id=?")
            values.append(self.run_id)
        if goal_revision is not None:
            terms += ["json_extract(payload,'$.instruction_revision')=?", "json_extract(payload,'$.goal_match')='matched'"]
            values.append(goal_revision)
        for supplied, operator, column in ((after, ">=", "end_time"), (before, "<=", "start_time")):
            if supplied:
                terms.append(f"{column}{operator}?")
                values.append(timestamp(supplied))
        if after and before and timestamp(after) > timestamp(before):
            raise ValueError("The history interval ends before it starts.")
        limit = min(max(int(limit), 1), 300)
        with self.connect() as db:
            if older_than:
                cursor = db.execute("SELECT start_time, revision FROM captions WHERE id=? AND " + " AND ".join(terms),
                                    [older_than, *values]).fetchone()
                if cursor is None:
                    raise ValueError("The observation is outside this view.")
                terms.append("(start_time,revision)<(?,?)")
                values.extend(cursor)
            count = db.execute("SELECT count(*) FROM captions WHERE " + " AND ".join(terms), values).fetchone()[0]
            rows = db.execute("SELECT revision,payload FROM captions WHERE " + " AND ".join(terms)
                              + " ORDER BY start_time DESC,revision DESC LIMIT ?", [*values, limit]).fetchall()
        return {"observations": [json.loads(row["payload"]) | {"revision": row["revision"]} for row in reversed(rows)],
                "omitted_count": max(0, count - len(rows)), "total_count": count}

    def frame(self, identity):
        with self.connect() as db:
            row = db.execute("""SELECT jpeg FROM snapshots JOIN captions ON caption_id=id
                WHERE id=? AND source_id=?""", (identity, self.source_id)).fetchone()
        return bytes(row[0]) if row else None

    def next_to_index(self, model):
        with self.connect() as db:
            row = db.execute("""SELECT payload FROM captions LEFT JOIN history_index ON history_index.caption_id=id
                LEFT JOIN index_retries ON index_retries.caption_id=id
                WHERE source_id=? AND (model IS NULL OR model!=?) AND (retry_after IS NULL OR retry_after<=?)
                ORDER BY revision LIMIT 1""",
                (self.source_id, model, time.time())).fetchone()
        return json.loads(row[0]) if row else None

    def retry_index(self, identity):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO index_retries VALUES (?,?)", (identity, time.time() + 30))

    def indexed(self, identity, model, sources):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO history_index VALUES (?,?,?)",
                       (identity, model, json.dumps(sources)))
            db.execute("DELETE FROM index_retries WHERE caption_id=?", (identity,))

    def index_scope(self, after, before, model):
        terms, values = ["source_id=?"], [self.source_id]
        for supplied, clause in ((after, "end_time>=?"), (before, "start_time<=?")):
            if supplied:
                terms.append(clause)
                values.append(timestamp(supplied))
        with self.connect() as db:
            return db.execute("""SELECT id,start_time,end_time, CASE WHEN model=? THEN sources END AS sources
                FROM captions LEFT JOIN history_index ON caption_id=id WHERE """ + " AND ".join(terms)
                + " ORDER BY start_time DESC, revision DESC", [model, *values]).fetchall()

    def index_counts(self, model):
        with self.connect() as db:
            total, indexed = db.execute("""SELECT count(*), count(CASE WHEN model=? THEN 1 END)
                FROM captions LEFT JOIN history_index ON caption_id=id WHERE source_id=?""",
                (model, self.source_id)).fetchone()
        return total, indexed

    def pending(self):
        with self.connect() as db:
            rows = db.execute("SELECT payload FROM captions WHERE published=0 AND source_id=? AND run_id=? ORDER BY revision LIMIT 300",
                              (self.source_id, self.run_id)).fetchall()
        return [json.loads(row[0]) for row in rows]

    def saved(self, identity, *, current_run=True):
        query = "SELECT payload FROM captions WHERE id=? AND source_id=?"
        values = [identity, self.source_id]
        if current_run:
            query += " AND run_id=?"
            values.append(self.run_id)
        with self.connect() as db:
            row = db.execute(query, values).fetchone()
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
