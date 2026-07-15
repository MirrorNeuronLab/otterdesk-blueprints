"""Run-scoped editable text knowledge store."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_KNOWLEDGE = """Business overview:
Otter Slice Pizza is a friendly neighborhood pizza shop. Help callers place
pickup or delivery orders from the editable menu knowledge.

Hours:
Open daily from 11:00 AM to 10:00 PM. Last delivery order is 9:30 PM.

Menu basics:
Signature pizzas include Margherita, Pepperoni Classic, Funghi, BBQ Chicken,
Veggie Garden, and Diablo. Ask for size, crust, sauce, toppings, quantity, and
pickup or delivery. Collect name and phone for pickup. Collect name, phone,
delivery address, and delivery notes for delivery.

Escalation:
Escalate allergies, food-safety concerns, refunds, complaints, payment-card
questions, missing orders, angry callers, and anything not grounded in the
knowledge text.
"""


@dataclass(frozen=True)
class KnowledgeMetadata:
    path: str
    bytes: int
    sha256: str
    updated_at: str

    def as_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "bytes": self.bytes,
            "sha256": self.sha256,
            "updated_at": self.updated_at,
        }


def default_knowledge_path() -> Path:
    return Path(__file__).resolve().parent / "knowledge" / "default_knowledge.txt"


def resolve_knowledge_path() -> Path:
    configured = os.getenv("CUSTOMER_SERVICE_KNOWLEDGE_PATH")
    if configured:
        return Path(configured).expanduser()
    run_dir = Path(os.getenv("MN_RUN_DIR") or os.getenv("CUSTOMER_SERVICE_RUN_DIR") or ".").expanduser()
    return run_dir / "knowledge" / "customer_service_knowledge.txt"


def load_seed_text() -> str:
    env_text = os.getenv("CUSTOMER_SERVICE_KNOWLEDGE_TEXT")
    if env_text:
        return env_text
    seed_path = default_knowledge_path()
    if seed_path.is_file():
        return seed_path.read_text(encoding="utf-8")
    return DEFAULT_KNOWLEDGE


def ensure_knowledge_file(path: Path | None = None, *, seed_text: str | None = None) -> Path:
    target = path or resolve_knowledge_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        write_knowledge(seed_text if seed_text is not None else load_seed_text(), target)
    return target


def read_knowledge(path: Path | None = None) -> str:
    target = ensure_knowledge_file(path)
    return target.read_text(encoding="utf-8")


def write_knowledge(text: str, path: Path | None = None) -> KnowledgeMetadata:
    target = path or resolve_knowledge_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    value = text if text.endswith("\n") else text + "\n"
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(target.parent), delete=False) as handle:
        handle.write(value)
        temp_name = handle.name
    Path(temp_name).replace(target)
    metadata = knowledge_metadata(target)
    (target.parent / "customer_service_knowledge.meta.json").write_text(
        json.dumps(metadata.as_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return metadata


def knowledge_metadata(path: Path | None = None) -> KnowledgeMetadata:
    target = path or resolve_knowledge_path()
    if not target.exists():
        size = 0
        digest = ""
        updated = datetime.now(timezone.utc)
    else:
        data = target.read_bytes()
        size = len(data)
        digest = hashlib.sha256(data).hexdigest()
        updated = datetime.fromtimestamp(target.stat().st_mtime, timezone.utc)
    return KnowledgeMetadata(
        path=str(target),
        bytes=size,
        sha256=digest,
        updated_at=updated.isoformat().replace("+00:00", "Z"),
    )
