"""Committed architecture task artifacts and atomic model-attempt reservations."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from mn_sdk.committed_artifacts import (
    CommittedJsonStore,
    CommittedArtifactRef,
    COMMITTED_JSON_VERSION,
)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


class CatalogStore:
    def __init__(self, run_dir, config=None):
        self.root = Path(run_dir).resolve()
        self.committed = CommittedJsonStore(self.root)

    def path(self, name):
        path = (self.root / name).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Catalog artifact escapes run directory")
        return path

    def read(self, name):
        return json.loads(self.path(name).read_text())

    def write(self, name, value):
        ref = self.committed.commit(name, value)
        return {"path": ref.path, "sha256": ref.sha256}

    def load_ref(self, ref):
        path = self.path(ref["path"])
        return self.committed.read(
            CommittedArtifactRef(
                type="artifact_ref",
                version=COMMITTED_JSON_VERSION,
                kind="json",
                path=ref["path"],
                sha256=ref["sha256"],
                size_bytes=path.stat().st_size,
            )
        )

    @contextmanager
    def ledger(self):
        path = self.path("catalog/budget.sqlite")
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path, timeout=30)
        try:
            db.execute(
                "CREATE TABLE IF NOT EXISTS attempts (task_id TEXT PRIMARY KEY, request_hash TEXT NOT NULL)"
            )
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def usage(self):
        with self.ledger() as db:
            return {
                "catalog_models": db.execute(
                    "SELECT count(*) FROM attempts"
                ).fetchone()[0]
            }

    def reservations(self):
        with self.ledger() as db:
            return dict(db.execute("SELECT task_id, request_hash FROM attempts"))

    def reserve(self, task_id, request_hash, limit):
        with self.ledger() as db:
            prior = db.execute(
                "SELECT request_hash FROM attempts WHERE task_id=?", (task_id,)
            ).fetchone()
            if prior:
                if prior[0] != request_hash:
                    raise ValueError("Model replay request changed")
                return "interrupted"
            if db.execute("SELECT count(*) FROM attempts").fetchone()[0] >= limit:
                return "exhausted"
            db.execute("INSERT INTO attempts VALUES (?,?)", (task_id, request_hash))
            return "reserved"

    def result(self, task_id):
        receipt = self.path(f"catalog/receipts/{task_id}.json")
        return (
            self.load_ref(self.read(str(receipt.relative_to(self.root))))
            if receipt.exists()
            else None
        )

    def results(self):
        return {
            p.stem: self.load_ref(self.read(str(p.relative_to(self.root))))
            for p in sorted(self.path("catalog/receipts").glob("*.json"))
        }

    def finish(self, task_id, value):
        ref = self.write(f"catalog/results/{task_id}.json", value)
        self.write(f"catalog/receipts/{task_id}.json", ref)
        return ref
