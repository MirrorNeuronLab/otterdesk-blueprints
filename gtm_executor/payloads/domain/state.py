"""Private durable marketing records; one SQLite transaction claims each side effect."""
import hashlib
import json
import sqlite3
from pathlib import Path
from contextlib import contextmanager


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


class State:
    def __init__(self, root):
        root = Path(root) / 'state' / 'marketing'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path = root / 'executor.sqlite3'
        with self.connection() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS records(kind TEXT, id TEXT, body TEXT NOT NULL, PRIMARY KEY(kind,id));
                CREATE TABLE IF NOT EXISTS attempts(id TEXT PRIMARY KEY, state TEXT NOT NULL, body TEXT NOT NULL);
            ''')
        self.path.chmod(0o600)

    @contextmanager
    def connection(self):
        with sqlite3.connect(self.path, timeout=15) as db:
            db.execute('PRAGMA synchronous=FULL')
            yield db

    def get(self, kind, key, default=None):
        with self.connection() as db:
            row = db.execute('SELECT body FROM records WHERE kind=? AND id=?',(kind,key)).fetchone()
        return json.loads(row[0]) if row else default

    def put(self, kind, key, body):
        with self.connection() as db:
            db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(kind,id) DO UPDATE SET body=excluded.body',(kind,key,json.dumps(body)))

    def items(self, kind):
        with self.connection() as db:
            return [(key,json.loads(body)) for key,body in db.execute('SELECT id,body FROM records WHERE kind=? ORDER BY id',(kind,))]

    def claim(self, key, body):
        with self.connection() as db:
            cursor = db.execute('INSERT OR IGNORE INTO attempts VALUES(?,?,?)',(key,'sending',json.dumps(body)))
            return cursor.rowcount == 1

    def receipt(self, key, status, body):
        with self.connection() as db:
            db.execute('UPDATE attempts SET state=?,body=? WHERE id=?',(status,json.dumps(body),key))

    def attempt(self, key):
        with self.connection() as db:
            row = db.execute('SELECT state,body FROM attempts WHERE id=?',(key,)).fetchone()
        return {'status':row[0], **json.loads(row[1])} if row else None

    def suppress(self, email, reason):
        self.put('suppression', email.strip().casefold(), {'reason':reason})

    def suppressed(self, email):
        return self.get('suppression',email.strip().casefold()) is not None
