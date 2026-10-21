"""Counsel-supplied review questions and handling decisions; never case evidence."""
import hashlib
import json
from datetime import date, datetime
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

VERSION = "mn.litigation.matter.v1"


def valid_timestamp(value):
    if not isinstance(value, str) or "T" not in value:
        return False
    try:
        return datetime.fromisoformat(value).utcoffset() is not None
    except ValueError:
        return False


def empty():
    return {"version": VERSION, "title": "", "intended_decision": "", "parties": [],
            "transaction_refs": [], "issues": [], "exclusions": [],
            "financial_events": [], "gap_assignments": []}


def prepare(context, inputs):
    value = empty()
    selected = inputs.get("matter_file")
    if selected:
        path = Path(selected)
        if path.is_symlink() or not path.is_file() or path.stat().st_size > 262144:
            raise ValueError("matter_file must be a regular JSON file no larger than 256 KiB")
        supplied = json.loads(path.read_text())
        schema = json.loads(Path(__file__).with_name("matter.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(supplied)
        for row in supplied.get("exclusions", []):
            if not valid_timestamp(row["reviewed_at"]):
                raise ValueError("Reviewed exclusions require an ISO timestamp with timezone")
        for collection, field in (("financial_events", "event_date"), ("gap_assignments", "internal_target")):
            for row in supplied.get(collection, []):
                if field in row:
                    date.fromisoformat(row[field])
        value.update(supplied)
    if len({row["id"] for row in value["issues"]}) != len(value["issues"]):
        raise ValueError("Counsel issue IDs must be unique")
    case = context.store.run_dir / "case"
    case.mkdir(parents=True, exist_ok=True)
    path = case / "matter.json"
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if path.exists() and path.read_text() != encoded:
        raise ValueError("Matter intake changed; create a fresh review run")
    path.write_text(encoded)
    return value


def load(root):
    path = Path(root) / "case/matter.json"
    return json.loads(path.read_text()) if path.exists() else empty()


def digest(root):
    return hashlib.sha256((Path(root) / "case/matter.json").read_bytes()).hexdigest()


def prompt_scope(matter):
    return {key: matter[key] for key in ("intended_decision", "parties", "transaction_refs", "issues")}
