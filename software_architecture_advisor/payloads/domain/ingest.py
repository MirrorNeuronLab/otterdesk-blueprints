"""Read-only source extraction and immutable RGX snapshot construction.

Static imports are dependencies, not runtime calls. SQL literals and declared
relationships retain their evidence class. Repository text is never executed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
from mn_sdk.model_access.runtime import runtime_model_json_request

from rfm_platform.documents import HashingEmbedder
from rfm_platform.embeddings import OpenAICompatibleEmbedder


EXTENSIONS = {".py", ".md", ".rst", ".txt", ".js", ".ts", ".tsx", ".java", ".go", ".rs", ".cs", ".sql"}


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def logical_id(value: str) -> int:
    return int(digest(value.encode())[:15], 16)


def make_embedder(config: dict):
    cfg = config["embedding"]
    if cfg["mode"] == "hash":
        return HashingEmbedder(dimensions=256)

    def request(payload):
        return runtime_model_json_request(
            'embedding', cfg['model'], '/embeddings', payload,
            provider=cfg['provider'], api_base=cfg.get('api_base'),
            timeout_seconds=config['llm']['timeout_seconds'], num_retries=0,
            required_capabilities=('embeddings',),
        )

    return OpenAICompatibleEmbedder(endpoint=cfg.get("api_base") or "managed://embedding", model=cfg["model"], requester=request)


class CachedEmbedder:
    def __init__(self, config: dict, cache: Path):
        self.provider = make_embedder(config)
        self.version = self.provider.version
        # Endpoint matters: two deployments can use the same name for different weights.
        self.namespace = json.dumps(config["embedding"], sort_keys=True)
        self.db = sqlite3.connect(cache)
        self.db.execute("CREATE TABLE IF NOT EXISTS vectors (key TEXT PRIMARY KEY, value TEXT)")
        self.hits = 0
        self.misses = 0
        self.dimension = None

    def embed(self, text: str) -> list[float]:
        key = digest((self.namespace + self.version + text).encode())
        row = self.db.execute("SELECT value FROM vectors WHERE key=?", (key,)).fetchone()
        if row:
            vector = json.loads(row[0])
            self.hits += 1
        else:
            method = getattr(self.provider, "embed_document", self.provider.embed)
            vector = list(method(text))
            self.db.execute("INSERT INTO vectors VALUES (?,?)", (key, json.dumps(vector)))
            self.misses += 1
        if not vector or any(not math.isfinite(v) for v in vector):
            raise ValueError("Invalid embedding")
        if self.dimension is not None and self.dimension != len(vector):
            raise ValueError("Embedding dimensions changed during ingestion")
        self.dimension = len(vector)
        return vector

    def close(self):
        self.db.commit()
        self.db.close()


def windows(text: str, size: int):
    # Exact character offsets and line numbers, including oversized single lines.
    start = 0
    while start < len(text):
        end = min(len(text), start + size)
        boundary = text.rfind("\n", start, end)
        if end < len(text) and boundary > start:
            end = boundary + 1
        yield start, end, text.count("\n", 0, start) + 1, text.count("\n", 0, max(start, end - 1)) + 1
        start = end


def module_name(path: str, roots: list[str]) -> str:
    value = Path(path)
    # Longest matching configured source root wins; src.pkg.foo -> pkg.foo.
    for root in sorted(roots, key=len, reverse=True):
        if root != ".":
            try:
                value = value.relative_to(root)
                break
            except ValueError:
                pass
    parts = list(value.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts) or "__root__"


def snapshot_repository(repository: Path, workspace: Path, config: dict, facts_path: Path | None = None, *, input_info=None) -> dict:
    from .capture import capture
    return capture(repository, workspace, config, facts_path, input_info)
