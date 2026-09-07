"""Durable architecture evidence records and run-wide investigation budgets."""
import hashlib
import json
import sqlite3
import time
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path


class BudgetExhausted(Exception):
    pass


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class InvestigationStore:
    def __init__(self, run_dir):
        self.root = Path(run_dir)
        self.context = read_json(self.root / "investigation-context.json")
        self.config = self.context["config"]

    def path(self, name):
        result = (self.root / name).resolve()
        if not result.is_relative_to(self.root.resolve()):
            raise ValueError("Investigation artifact escapes run directory")
        return result

    def read(self, name):
        return read_json(self.path(name))

    def write(self, name, value):
        path = self.path(name)
        immutable = name.startswith(("investigation/plans/", "investigation/parameters/", "investigation/findings/", "investigation/observations/", "investigation/rounds/"))
        if immutable and path.exists():
            if read_json(path) != value:
                raise ValueError("Immutable investigation artifact already exists with different contents")
        else:
            write_json(path, value)
        return {"path": name, "sha256": hashlib.sha256(self.path(name).read_bytes()).hexdigest()}

    def load_ref(self, ref):
        path = self.path(ref["path"])
        if hashlib.sha256(path.read_bytes()).hexdigest() != ref["sha256"]:
            raise ValueError("Investigation artifact hash mismatch")
        return read_json(path)

    @contextmanager
    def ledger(self):
        connection = sqlite3.connect(self.root / "investigation-budget.sqlite", timeout=30)
        try:
            connection.execute("CREATE TABLE IF NOT EXISTS usage (kind TEXT PRIMARY KEY, count INTEGER NOT NULL)")
            connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def usage(self):
        with self.ledger() as db:
            return dict(db.execute("SELECT kind, count FROM usage"))

    def reserve(self, kind, *, final=False):
        cfg = self.config
        if time.time() >= self.context["deadline"]:
            raise BudgetExhausted("investigation deadline reached")
        limit = cfg["llm"]["max_calls"] if kind == "models" else cfg["investigation"]["max_queries"]
        if kind == "models" and not final:
            limit -= cfg["investigation"]["final_model_reserve"]
        with self.ledger() as db:
            row = db.execute("SELECT count FROM usage WHERE kind=?", (kind,)).fetchone()
            count = row[0] if row else 0
            if count >= limit:
                raise BudgetExhausted(f"{kind} budget reached")
            db.execute("INSERT INTO usage VALUES (?,1) ON CONFLICT(kind) DO UPDATE SET count=count+1", (kind,))

    def results(self):
        return [read_json(path) for path in sorted((self.root / "investigation/observations").glob("*.json"))]

    def findings(self):
        latest = {}
        for path in sorted((self.root / "investigation/findings").glob("*.json")):
            finding = read_json(path)
            latest[finding["id"]] = finding
        for path in sorted(self.root.glob("investigation/plans/retirements-*.json")):
            for retirement in read_json(path):
                if retirement["id"] in latest:
                    latest[retirement["id"]]["retirement"] = retirement
        return list(latest.values())


class RecordedModel:
    """Journal architecture model requests, including lazy graph inference."""
    def __init__(self, store, node_id, client=None, final=False):
        from .model import JsonModel
        self.store, self.node_id, self.final = store, node_id, final
        self.model = JsonModel(store.config, client=client)
        self.calls = self.model.calls
        self.ordinal = 0

    def complete(self, instruction, data):
        key = f"investigation/models/{self.node_id}-{self.ordinal:03d}.json"
        self.ordinal += 1
        digest = hashlib.sha256(json.dumps([instruction, data], sort_keys=True).encode()).hexdigest()
        path = self.store.path(key)
        if path.exists():
            prior = read_json(path)
            if prior["request_hash"] != digest:
                raise ValueError("Model replay context changed")
            if prior["status"] != "completed":
                raise RuntimeError("Prior model request has no durable response; explicit retry review required")
            self.calls.append(prior["trace"])
            return deepcopy(prior["value"])
        self.store.reserve("models", final=self.final)
        self.store.write(key, {"request_hash": digest, "status": "started"})
        self.model.config = {**self.model.config, "timeout_seconds": min(self.model.config["timeout_seconds"], max(1, self.store.context["deadline"] - time.time()))}
        try:
            value = self.model.complete(instruction, data)
        except Exception as exc:
            self.store.write(key, {"request_hash": digest, "status": "failed", "error": str(exc),
                                  "trace": self.calls[-1] if self.calls else {}})
            raise
        self.store.write(key, {"request_hash": digest, "status": "completed", "value": value, "trace": self.calls[-1]})
        return value


def task_input(store, work):
    if "task" not in work:
        raise ValueError("A committed task artifact is required")
    parameters = store.load_ref(work["task"])
    if not isinstance(parameters, dict) or "context" in parameters or "_child" in parameters:
        raise ValueError("Invalid task parameters")
    return {**parameters, "context": work["context"], "_child": work.get("_child", {})}


def record_failure(context, work, error):
    root = Path(context["run_dir"])
    traces = [read_json(path) for path in sorted(root.glob("investigation/models/*.json"))]
    write_json(root / "model-trace.json", traces)
    write_json(root / "investigation.json", {"schema_version": "mn.architecture.investigation.v2",
        "status": "failed", "errors": [f"{type(error).__name__}: {error}"],
        "child_revision": work.get("_child", {}).get("revision"),
        "audit_directory": "investigation/"})
