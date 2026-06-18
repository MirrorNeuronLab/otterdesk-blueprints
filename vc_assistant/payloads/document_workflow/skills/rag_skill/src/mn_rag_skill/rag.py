from __future__ import annotations

from array import array
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
from pathlib import Path
from typing import Any, Iterable
from urllib import error as urlerror
from urllib import request as urlrequest
from urllib.parse import urlparse


DEFAULT_REDIS_URL = "redis://127.0.0.1:6379/0"
DEFAULT_NAMESPACE = "mirror_neuron_rag"
DEFAULT_EMBEDDING_PROVIDER = "docker_model_runner"
DEFAULT_EMBEDDING_MODEL = "hf.co/jinaai/jina-embeddings-v5-text-small-retrieval:Q4_K_M"
DEFAULT_EMBEDDING_API_BASE = "http://localhost:12434/engines/v1"
DEFAULT_EMBEDDING_QUERY_PREFIX = "Query: "
DEFAULT_EMBEDDING_DOCUMENT_PREFIX = "Document: "
DEFAULT_EMBEDDING_START_COMMAND = ""
DEFAULT_SENTENCE_TRANSFORMER_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
DEFAULT_VECTOR_DIM = 1024
SUPPORTED_KNOWLEDGE_SUFFIXES = {".md", ".txt", ".json", ".yaml", ".yml"}
RAG_STATE_FILENAME = ".mn-rag-state.json"
GENERATED_RAG_DIR_NAMES = {
    "__pycache__",
    ".cache",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".git",
    ".venv",
    "artifacts",
    "cache",
    "checkpoints",
    "context_engine",
    "events",
    "log",
    "logs",
    "memory",
    "metrics",
    "monitoring",
    "observability",
    "output",
    "outputs",
    "run",
    "run_store",
    "runs",
    "state",
    "states",
    "temp",
    "tmp",
    "trace",
    "traces",
}
GENERATED_RAG_FILE_NAMES = {
    RAG_STATE_FILENAME,
    "default.json",
    "events.json",
    "events.jsonl",
    "llm_rag_trace.json",
    "llm_rag_trace.jsonl",
    "logs.json",
    "logs.jsonl",
    "manifest.json",
    "monitor_state.json",
    "observability.json",
    "observability.jsonl",
    "overwrite.json",
    "resources.json",
    "resources.jsonl",
    "run_manifest.json",
    "run_state.json",
    "scenario.json",
    "stderr.json",
    "stderr.jsonl",
    "stdout.json",
    "stdout.jsonl",
    "trace.json",
    "trace.jsonl",
    "watch_state.json",
}
GENERATED_RAG_SUFFIXES = {
    ".db",
    ".db-shm",
    ".db-wal",
    ".jsonl",
    ".lock",
    ".log",
    ".pyc",
    ".pyo",
    ".sqlite",
    ".sqlite3",
    ".tmp",
}
GENERATED_RAG_FILE_PREFIXES = (
    "events.",
    "logs.",
    "metrics.",
    "observability.",
    "resources.",
    "runtime.",
    "stderr.",
    "stdout.",
    "trace.",
)
GENERATED_RAG_FILE_SUFFIXES = (
    "-events.json",
    "-logs.json",
    "-state.json",
    "-trace.json",
    ".events.json",
    ".logs.json",
    ".state.json",
    ".trace.json",
    "_events.json",
    "_logs.json",
    "_state.json",
    "_trace.json",
)


class RagError(RuntimeError):
    """Raised when Redis RAG indexing or retrieval cannot complete."""


def _env_value(name: str, default: str) -> str:
    return os.environ.get(name, "").strip() or default


def _first_env_value(names: tuple[str, ...], default: str) -> str:
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return default


def _safe_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())
    token = token.strip("._-")
    return token or "default"


def _blueprint_namespace(base: str, blueprint_id: str) -> str:
    safe_base = _safe_token(base or DEFAULT_NAMESPACE)
    safe_blueprint = _safe_token(blueprint_id)
    if safe_blueprint and safe_blueprint not in safe_base:
        return _safe_token(f"{safe_base}_{safe_blueprint}")
    return safe_base


def _validate_redis_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"redis", "rediss"}:
        raise ValueError("Redis URL must use redis:// or rediss://")
    return value


def _as_bool(value: Any, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _as_config_string(value: Any, default: str = "") -> str:
    if value is None:
        return default
    return str(value)


@dataclass
class RagConfig:
    redis_url: str | None = None
    namespace: str | None = None
    blueprint_id: str = "default"
    embedding_provider: str = DEFAULT_EMBEDDING_PROVIDER
    embedding_model: str = DEFAULT_EMBEDDING_MODEL
    embedding_api_base: str = DEFAULT_EMBEDDING_API_BASE
    embedding_query_prefix: str = DEFAULT_EMBEDDING_QUERY_PREFIX
    embedding_document_prefix: str = DEFAULT_EMBEDDING_DOCUMENT_PREFIX
    embedding_start_command: str = DEFAULT_EMBEDDING_START_COMMAND
    embedding_healthcheck_enabled: bool = True
    index_name: str = ""
    key_prefix: str = ""
    chunk_size: int = 220
    chunk_overlap: int = 40
    top_k: int = 5
    vector_dim: int = DEFAULT_VECTOR_DIM
    required: bool = False

    def __post_init__(self) -> None:
        self.blueprint_id = _safe_token(self.blueprint_id)
        self.redis_url = _validate_redis_url(
            self.redis_url
            or _first_env_value(("MN_RAG_REDIS_URL", "MN_BLUEPRINT_RAG_REDIS_URL", "MN_REDIS_URL"), DEFAULT_REDIS_URL)
        )
        if self.namespace:
            self.namespace = _safe_token(self.namespace)
        else:
            self.namespace = _blueprint_namespace(
                _first_env_value(("MN_RAG_REDIS_NAMESPACE", "MN_BLUEPRINT_RAG_NAMESPACE"), DEFAULT_NAMESPACE),
                self.blueprint_id,
            )
        self.embedding_provider = _safe_token(self.embedding_provider or DEFAULT_EMBEDDING_PROVIDER)
        if not self.embedding_model:
            self.embedding_model = (
                DEFAULT_SENTENCE_TRANSFORMER_MODEL
                if self.embedding_provider in {"sentence_transformers", "sentence-transformers"}
                else DEFAULT_EMBEDDING_MODEL
            )
        self.embedding_api_base = (self.embedding_api_base or DEFAULT_EMBEDDING_API_BASE).rstrip("/")
        self.embedding_query_prefix = str(self.embedding_query_prefix or "")
        self.embedding_document_prefix = str(self.embedding_document_prefix or "")
        self.embedding_start_command = str(self.embedding_start_command or "")
        self.embedding_healthcheck_enabled = _as_bool(self.embedding_healthcheck_enabled, True)
        self.chunk_size = max(40, int(self.chunk_size or 220))
        self.chunk_overlap = max(0, min(int(self.chunk_overlap or 0), self.chunk_size - 1))
        self.top_k = max(1, int(self.top_k or 5))
        self.vector_dim = max(1, int(self.vector_dim or DEFAULT_VECTOR_DIM))
        if not self.key_prefix:
            self.key_prefix = f"{self.namespace}:rag:{self.blueprint_id}"
        if not self.index_name:
            self.index_name = f"idx:{self.namespace}:rag:{self.blueprint_id}"

    @classmethod
    def from_mapping(cls, values: dict[str, Any] | None, *, blueprint_id: str = "default") -> "RagConfig":
        values = values or {}
        return cls(
            redis_url=values.get("redis_url") or None,
            namespace=values.get("namespace") or None,
            blueprint_id=str(values.get("blueprint_id") or blueprint_id),
            embedding_provider=str(values.get("embedding_provider") or DEFAULT_EMBEDDING_PROVIDER),
            embedding_model=str(values.get("embedding_model") or ""),
            embedding_api_base=str(values.get("embedding_api_base") or DEFAULT_EMBEDDING_API_BASE),
            embedding_query_prefix=_as_config_string(values.get("embedding_query_prefix"), DEFAULT_EMBEDDING_QUERY_PREFIX),
            embedding_document_prefix=_as_config_string(values.get("embedding_document_prefix"), DEFAULT_EMBEDDING_DOCUMENT_PREFIX),
            embedding_start_command=_as_config_string(values.get("embedding_start_command"), DEFAULT_EMBEDDING_START_COMMAND),
            embedding_healthcheck_enabled=_as_bool(values.get("embedding_healthcheck_enabled"), True),
            index_name=str(values.get("index_name") or ""),
            key_prefix=str(values.get("key_prefix") or ""),
            chunk_size=_as_int(values.get("chunk_size"), 220),
            chunk_overlap=_as_int(values.get("chunk_overlap"), 40),
            top_k=_as_int(values.get("top_k"), 5),
            vector_dim=_as_int(values.get("vector_dim"), DEFAULT_VECTOR_DIM),
            required=_as_bool(values.get("required"), False),
        )


@dataclass
class RagChunk:
    chunk_id: str
    text: str
    path: str
    heading: str
    blueprint_id: str
    source_hash: str
    source_mtime: float
    section: str = ""
    score: float = 0.0
    key: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class RagIndexSummary:
    blueprint_id: str
    namespace: str
    knowledge_dir: str
    index_name: str
    key_prefix: str
    embedding_provider: str
    embedding_model: str
    vector_dim: int
    indexed_count: int
    deleted_count: int
    skipped_count: int
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._model: Any | None = None

    @property
    def model(self) -> Any:
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except Exception as exc:  # pragma: no cover - depends on optional package
                raise RagError("Install sentence-transformers to use the default RAG embedder.") from exc
            self._model = SentenceTransformer(self.model_name)
        return self._model

    def encode(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        encoded = self.model.encode(texts)
        return [_as_float_list(item) for item in encoded]


class DockerModelRunnerEmbedder:
    def __init__(self, config: RagConfig, urlopen: Any | None = None) -> None:
        self.config = config
        self._urlopen = urlopen or urlrequest.urlopen

    def _prefix(self, input_type: str) -> str:
        if input_type == "query":
            return self.config.embedding_query_prefix
        return self.config.embedding_document_prefix

    def encode(self, texts: list[str], input_type: str = "document") -> list[list[float]]:
        if not texts:
            return []
        prefixed = [f"{self._prefix(input_type)}{text}" for text in texts]
        payload = json.dumps({"model": self.config.embedding_model, "input": prefixed}).encode("utf-8")
        endpoint = f"{self.config.embedding_api_base}/embeddings"
        request = urlrequest.Request(
            endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with self._urlopen(request, timeout=120) as response:
                body = json.loads(response.read().decode("utf-8"))
        except urlerror.HTTPError as exc:  # pragma: no cover - depends on live endpoint
            detail = exc.read().decode("utf-8", errors="replace")
            raise RagError(f"Docker Model Runner embeddings request failed: HTTP {exc.code} {detail}") from exc
        except Exception as exc:  # pragma: no cover - depends on live endpoint
            raise RagError(f"Docker Model Runner embeddings request failed at {endpoint}: {exc}") from exc
        data = body.get("data") if isinstance(body, dict) else None
        if not isinstance(data, list):
            raise RagError("Docker Model Runner embeddings response did not include a data list.")
        ordered = sorted(data, key=lambda item: int((item or {}).get("index", 0)))
        vectors = [_as_float_list((item or {}).get("embedding")) for item in ordered]
        if len(vectors) != len(texts):
            raise RagError(f"Docker Model Runner returned {len(vectors)} embeddings for {len(texts)} inputs.")
        if any(not vector for vector in vectors):
            raise RagError("Docker Model Runner returned an empty embedding vector.")
        return vectors


class MemoryRagStore:
    """Small in-memory store for deterministic unit tests."""

    def __init__(self) -> None:
        self.records: dict[str, dict[str, Any]] = {}
        self.indexes: dict[str, int] = {}
        self.metadata: dict[str, dict[str, str]] = {}

    def ensure_index(self, config: RagConfig, vector_dim: int) -> None:
        self.indexes[config.index_name] = vector_dim

    def keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.records if key.startswith(prefix))

    def upsert(self, key: str, record: dict[str, Any]) -> None:
        self.records[key] = dict(record)

    def delete(self, *keys: str) -> int:
        count = 0
        for key in keys:
            if key in self.records:
                del self.records[key]
                count += 1
            if key in self.metadata:
                del self.metadata[key]
                count += 1
        return count

    def hset(self, key: str, mapping: dict[str, Any]) -> int:
        current = self.metadata.setdefault(key, {})
        current.update({str(name): _decode(value) for name, value in mapping.items()})
        return len(mapping)

    def hget(self, key: str, name: str) -> str:
        return self.metadata.get(key, {}).get(name, "")

    def query(self, config: RagConfig, query_vector: list[float], top_k: int, filters: dict[str, Any] | None = None) -> list[RagChunk]:
        filters = filters or {}
        results: list[RagChunk] = []
        for key in self.keys(f"{config.key_prefix}:"):
            record = self.records[key]
            if any(str(record.get(name) or "") != str(value) for name, value in filters.items() if value):
                continue
            score = _cosine_similarity(query_vector, _as_float_list(record.get("embedding") or []))
            results.append(_chunk_from_record(key, record, score))
        return sorted(results, key=lambda item: item.score, reverse=True)[:top_k]


def _as_float_list(value: Any) -> list[float]:
    if value is None:
        return []
    if hasattr(value, "tolist"):
        value = value.tolist()
    return [float(item) for item in value]


def _connect_redis(config: RagConfig) -> Any:
    try:
        import redis
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RagError("Install redis to use Redis-backed RAG storage.") from exc
    return redis.Redis.from_url(config.redis_url, decode_responses=False)


def _vector_to_bytes(vector: list[float]) -> bytes:
    return array("f", vector).tobytes()


def _index_meta_key(config: RagConfig) -> str:
    return f"{config.namespace}:rag_meta:{config.blueprint_id}"


def _vector_set_key(config: RagConfig) -> str:
    return f"{config.key_prefix}:vectors"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    dot = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _decode(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return str(value or "")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, ensure_ascii=True)


def _json_loads(value: Any) -> Any:
    try:
        return json.loads(_decode(value))
    except Exception:
        return {}


def _decoded_mapping(record: dict[Any, Any]) -> dict[str, Any]:
    return {_decode(key): value for key, value in (record or {}).items()}


def _redis_vector_sets_supported(client: Any) -> bool:
    try:
        info = client.execute_command("COMMAND", "INFO", "VADD")
        return bool(info and info != [None])
    except Exception:
        return False


def _vector_dim_from_info_value(value: Any) -> int | None:
    if isinstance(value, dict):
        lowered = {_decode(key).lower(): item for key, item in value.items()}
        labels = {_decode(item).lower() for item in value.values() if isinstance(item, (str, bytes))}
        if "embedding" in labels:
            for key in ("dim", "dimension"):
                if key in lowered:
                    try:
                        return int(_decode(lowered[key]))
                    except Exception:
                        return None
        for item in value.values():
            found = _vector_dim_from_info_value(item)
            if found:
                return found
    if isinstance(value, (list, tuple)):
        text_items = [_decode(item).lower() for item in value]
        if "embedding" in text_items and "dim" in text_items:
            dim_index = text_items.index("dim") + 1
            if dim_index < len(value):
                try:
                    return int(_decode(value[dim_index]))
                except Exception:
                    return None
        for item in value:
            found = _vector_dim_from_info_value(item)
            if found:
                return found
    return None


def _existing_index_vector_dim(info: Any) -> int | None:
    return _vector_dim_from_info_value(info)


def _file_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _file_bytes_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _section_id(heading: str) -> str:
    return _safe_token(heading.lower().replace(" ", "_"))[:80]


def _is_generated_or_runtime_path(rel_path: Path) -> bool:
    parts = rel_path.parts
    if not parts:
        return True
    lowered_parts = [part.lower() for part in parts]
    if any(part.startswith(".") for part in parts):
        return True
    if any(part in GENERATED_RAG_DIR_NAMES for part in lowered_parts[:-1]):
        return True
    name = lowered_parts[-1]
    if name in GENERATED_RAG_FILE_NAMES:
        return True
    if Path(name).suffix.lower() in GENERATED_RAG_SUFFIXES:
        return True
    if any(name.startswith(prefix) for prefix in GENERATED_RAG_FILE_PREFIXES):
        return True
    return any(name.endswith(suffix) for suffix in GENERATED_RAG_FILE_SUFFIXES)


def _is_rag_knowledge_file(root: Path, path: Path, *, supported_only: bool) -> bool:
    if not path.is_file():
        return False
    rel_path = path.relative_to(root)
    if _is_generated_or_runtime_path(rel_path):
        return False
    return not supported_only or path.suffix.lower() in SUPPORTED_KNOWLEDGE_SUFFIXES


def _iter_knowledge_files(knowledge_dir: Path) -> Iterable[Path]:
    if not knowledge_dir.exists():
        return []
    return (
        path
        for path in sorted(knowledge_dir.rglob("*"))
        if _is_rag_knowledge_file(knowledge_dir, path, supported_only=True)
    )


def _iter_all_knowledge_files(knowledge_dir: Path) -> Iterable[Path]:
    if not knowledge_dir.exists():
        return []
    return (
        path
        for path in sorted(knowledge_dir.rglob("*"))
        if _is_rag_knowledge_file(knowledge_dir, path, supported_only=False)
    )


def _manifest_digest(files: list[dict[str, Any]]) -> str:
    payload = [
        {
            "path": item.get("path"),
            "sha256": item.get("sha256"),
            "size_bytes": item.get("size_bytes"),
            "supported": bool(item.get("supported")),
        }
        for item in files
    ]
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def knowledge_manifest(knowledge_dir: str | Path) -> dict[str, Any]:
    root = Path(knowledge_dir).expanduser().resolve()
    files: list[dict[str, Any]] = []
    for path in _iter_all_knowledge_files(root):
        stats = path.stat()
        suffix = path.suffix.lower()
        files.append(
            {
                "path": path.relative_to(root).as_posix(),
                "size_bytes": int(stats.st_size),
                "mtime": float(stats.st_mtime),
                "sha256": _file_bytes_hash(path),
                "supported": suffix in SUPPORTED_KNOWLEDGE_SUFFIXES,
                "suffix": suffix,
            }
        )
    supported_files = [item for item in files if item.get("supported")]
    return {
        "knowledge_dir": str(root),
        "files": files,
        "manifest_hash": _manifest_digest(files),
        "index_manifest_hash": _manifest_digest(supported_files),
        "supported_count": len(supported_files),
        "total_count": len(files),
    }


def _state_path(knowledge_dir: Path) -> Path:
    return knowledge_dir / RAG_STATE_FILENAME


def _read_local_rag_state(knowledge_dir: Path) -> dict[str, Any]:
    try:
        state = json.loads(_state_path(knowledge_dir).read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _write_local_rag_state(knowledge_dir: Path, state: dict[str, Any]) -> None:
    try:
        knowledge_dir.mkdir(parents=True, exist_ok=True)
        target = _state_path(knowledge_dir)
        tmp = target.with_suffix(f"{target.suffix}.tmp")
        tmp.write_text(f"{json.dumps(state, indent=2, sort_keys=True, ensure_ascii=True)}\n", encoding="utf-8")
        tmp.replace(target)
    except Exception:
        pass


def _read_redis_rag_state(config: RagConfig, redis_client: Any | None = None) -> dict[str, Any]:
    try:
        client = redis_client or _connect_redis(config)
        raw = client.hget(_index_meta_key(config), "rag_state")
        state = _json_loads(raw)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _write_redis_rag_state(config: RagConfig, state: dict[str, Any], redis_client: Any | None = None) -> None:
    try:
        client = redis_client or _connect_redis(config)
        client.hset(
            _index_meta_key(config),
            mapping={
                "rag_state": _json_dumps(state),
                "manifest_hash": str(state.get("manifest_hash") or ""),
                "index_manifest_hash": str(state.get("index_manifest_hash") or ""),
                "last_indexed_at": str(state.get("last_indexed_at") or ""),
                "index_name": config.index_name,
                "key_prefix": config.key_prefix,
                "blueprint_id": config.blueprint_id,
                "embedding_provider": config.embedding_provider,
                "embedding_model": config.embedding_model,
            },
        )
    except Exception:
        pass


def _previous_rag_state(knowledge_dir: Path, config: RagConfig, redis_client: Any | None = None) -> dict[str, Any]:
    try:
        client = redis_client or _connect_redis(config)
        raw = client.hget(_index_meta_key(config), "rag_state")
        state = _json_loads(raw)
        return state if isinstance(state, dict) else {}
    except Exception:
        return {}


def _changed_paths(previous: dict[str, Any], current_manifest: dict[str, Any]) -> dict[str, set[str]]:
    previous_files = {str(item.get("path")): item for item in previous.get("files") or [] if isinstance(item, dict)}
    current_files = {str(item.get("path")): item for item in current_manifest.get("files") or [] if isinstance(item, dict)}
    added = set(current_files) - set(previous_files)
    removed = set(previous_files) - set(current_files)
    changed = {
        path
        for path, item in current_files.items()
        if path in previous_files
        and (
            str(item.get("sha256") or "") != str(previous_files[path].get("sha256") or "")
            or int(item.get("size_bytes") or 0) != int(previous_files[path].get("size_bytes") or 0)
            or bool(item.get("supported")) != bool(previous_files[path].get("supported"))
        )
    }
    return {"added": added, "changed": changed, "removed": removed}


def _state_files(current_manifest: dict[str, Any], previous: dict[str, Any], indexed_at: str = "", failed: bool = False) -> list[dict[str, Any]]:
    paths = _changed_paths(previous, current_manifest)
    files: list[dict[str, Any]] = []
    for item in current_manifest.get("files") or []:
        if not isinstance(item, dict):
            continue
        path = str(item.get("path") or "")
        status = "unsupported"
        if item.get("supported"):
            if failed:
                status = "failed"
            elif path in paths["added"]:
                status = "new"
            elif path in paths["changed"]:
                status = "changed"
            else:
                status = "ready"
        files.append({**item, "status": status, "indexed_at": indexed_at if status == "ready" else ""})
    for path in sorted(paths["removed"]):
        previous_item = {**(next((item for item in previous.get("files") or [] if isinstance(item, dict) and item.get("path") == path), {}) or {})}
        if previous_item:
            files.append({**previous_item, "status": "removed", "indexed_at": ""})
    return files


def _public_state_from_manifest(
    *,
    config: RagConfig,
    current_manifest: dict[str, Any],
    previous: dict[str, Any],
    status: str,
    changed: bool,
    indexed_at: str = "",
    warnings: list[Any] | None = None,
    index_summary: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "enabled": True,
        "status": status,
        "knowledge_dir": current_manifest.get("knowledge_dir"),
        "manifest_hash": current_manifest.get("manifest_hash"),
        "index_manifest_hash": current_manifest.get("index_manifest_hash"),
        "changed": changed,
        "last_indexed_at": indexed_at or previous.get("last_indexed_at") or "",
        "files": _state_files(current_manifest, previous, indexed_at or previous.get("last_indexed_at") or "", failed=status == "knowledge_rag_failed"),
        "index_summary": index_summary or previous.get("index_summary") or {},
        "warnings": list(warnings or []),
        "config": {
            "blueprint_id": config.blueprint_id,
            "namespace": config.namespace,
            "index_name": config.index_name,
            "key_prefix": config.key_prefix,
            "embedding_provider": config.embedding_provider,
            "embedding_model": config.embedding_model,
            "top_k": config.top_k,
            "vector_dim": config.vector_dim,
            "required": config.required,
        },
    }


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _heading_sections(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, list[str]]] = []
    heading = ""
    lines: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s{0,3}(#{1,6})\s+(.+?)\s*$", line)
        if match:
            if lines:
                sections.append((heading, lines))
            heading = match.group(2).strip()
            lines = [line]
        else:
            lines.append(line)
    if lines:
        sections.append((heading, lines))
    return [(heading, "\n".join(lines).strip()) for heading, lines in sections if "\n".join(lines).strip()]


def _word_windows(text: str, chunk_size: int, chunk_overlap: int) -> list[str]:
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        if end >= len(words):
            break
        start = max(0, end - chunk_overlap)
    return chunks


def _make_chunk(
    *,
    config: RagConfig,
    rel_path: str,
    heading: str,
    text: str,
    source_hash: str,
    source_mtime: float,
    ordinal: int,
) -> RagChunk:
    chunk_hash = hashlib.sha256(f"{rel_path}\0{heading}\0{ordinal}\0{text}".encode("utf-8")).hexdigest()
    section = _section_id(heading or Path(rel_path).stem)
    return RagChunk(
        chunk_id=chunk_hash[:32],
        text=text,
        path=rel_path,
        heading=heading or Path(rel_path).stem,
        blueprint_id=config.blueprint_id,
        source_hash=source_hash,
        source_mtime=source_mtime,
        section=section,
        metadata={"ordinal": ordinal, "embedding_model": config.embedding_model},
    )


def chunk_knowledge_dir(knowledge_dir: str | Path, config: RagConfig) -> list[RagChunk]:
    root = Path(knowledge_dir).expanduser().resolve()
    chunks: list[RagChunk] = []
    for path in _iter_knowledge_files(root):
        text = _read_text(path)
        if not text.strip():
            continue
        source_hash = _file_hash(text)
        source_mtime = path.stat().st_mtime
        rel_path = path.relative_to(root).as_posix()
        ordinal = 0
        for heading, section_text in _heading_sections(text):
            for window in _word_windows(section_text, config.chunk_size, config.chunk_overlap):
                ordinal += 1
                chunks.append(
                    _make_chunk(
                        config=config,
                        rel_path=rel_path,
                        heading=heading,
                        text=window,
                        source_hash=source_hash,
                        source_mtime=source_mtime,
                        ordinal=ordinal,
                    )
                )
    return chunks


def build_embedder(config: RagConfig) -> Any:
    provider = _safe_token(config.embedding_provider or DEFAULT_EMBEDDING_PROVIDER)
    if provider in {"docker_model_runner", "docker-model-runner"}:
        return DockerModelRunnerEmbedder(config)
    if provider in {"sentence_transformers", "sentence-transformers", "sentence_transformer", "sentence-transformer"}:
        return SentenceTransformerEmbedder(config.embedding_model or DEFAULT_SENTENCE_TRANSFORMER_MODEL)
    raise RagError(f"Unsupported RAG embedding provider: {config.embedding_provider}")


def ensure_embedding_backend(config: RagConfig) -> dict[str, Any]:
    if config.embedding_provider not in {"docker_model_runner", "docker-model-runner"}:
        return {"status": "not_required", "embedding_provider": config.embedding_provider}
    result: dict[str, Any] = {
        "status": "ready",
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_api_base": config.embedding_api_base,
        "start_command": config.embedding_start_command,
    }
    if config.embedding_start_command:
        try:
            completed = subprocess.run(
                shlex.split(config.embedding_start_command),
                capture_output=True,
                text=True,
                timeout=600,
                check=False,
            )
        except Exception as exc:  # pragma: no cover - depends on local Docker
            raise RagError(f"Could not start Docker Model Runner embedding model: {exc}") from exc
        result["start_returncode"] = completed.returncode
        result["start_stdout"] = (completed.stdout or "").strip()[:2000]
        result["start_stderr"] = (completed.stderr or "").strip()[:2000]
        if completed.returncode != 0:
            raise RagError(
                "Docker Model Runner embedding start command failed: "
                f"{completed.stderr or completed.stdout or completed.returncode}"
            )
    if config.embedding_healthcheck_enabled:
        vector = DockerModelRunnerEmbedder(config).encode(["healthcheck"], input_type="query")[0]
        result["healthcheck_vector_dim"] = len(vector)
    return result


def _embed_texts(
    texts: list[str],
    config: RagConfig,
    embedder: Any | None = None,
    *,
    input_type: str = "document",
) -> list[list[float]]:
    if not texts:
        return []
    embedder = embedder or build_embedder(config)
    try:
        encoded = embedder.encode(texts, input_type=input_type)
    except TypeError:
        encoded = embedder.encode(texts)
    return [_as_float_list(item) for item in encoded]


def ensure_index(config: RagConfig, vector_dim: int | None = None, redis_client: Any | None = None) -> dict[str, Any]:
    vector_dim = int(vector_dim or config.vector_dim)
    client = redis_client or _connect_redis(config)
    if isinstance(client, MemoryRagStore):
        client.ensure_index(config, vector_dim)
        return {"status": "ok", "index_name": config.index_name, "vector_dim": vector_dim, "store": "memory"}
    try:
        from redis.commands.search.field import NumericField, TagField, TextField, VectorField
        from redis.commands.search.index_definition import IndexDefinition, IndexType
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RagError("Install redis with RediSearch command support to create RAG indexes.") from exc
    try:
        info = client.ft(config.index_name).info()
        existing_dim = _existing_index_vector_dim(info)
        if not existing_dim:
            try:
                existing_dim = int(_decode(client.hget(_index_meta_key(config), "vector_dim") or "0") or 0)
            except Exception:
                existing_dim = None
        if existing_dim and existing_dim != vector_dim:
            client.ft(config.index_name).dropindex(delete_documents=False)
        else:
            try:
                client.hset(
                    _index_meta_key(config),
                    mapping={
                        "index_name": config.index_name,
                        "key_prefix": config.key_prefix,
                        "blueprint_id": config.blueprint_id,
                        "embedding_provider": config.embedding_provider,
                        "embedding_model": config.embedding_model,
                        "vector_dim": str(vector_dim),
                    },
                )
            except Exception:
                pass
            return {"status": "exists", "index_name": config.index_name, "vector_dim": vector_dim, "info": _decode(info)}
    except Exception:
        pass
    schema = (
        TextField("text"),
        TagField("blueprint_id"),
        TagField("path"),
        TextField("heading"),
        TagField("section"),
        TagField("embedding_model"),
        NumericField("source_mtime"),
        VectorField(
            "embedding",
            "FLAT",
            {
                "TYPE": "FLOAT32",
                "DIM": vector_dim,
                "DISTANCE_METRIC": "COSINE",
            },
        ),
    )
    definition = IndexDefinition(prefix=[f"{config.key_prefix}:"], index_type=IndexType.HASH)
    try:
        client.ft(config.index_name).create_index(fields=schema, definition=definition)
    except Exception as exc:
        if _redis_vector_sets_supported(client):
            vector_set_key = _vector_set_key(config)
            try:
                existing_dim = int(_decode(client.execute_command("VDIM", vector_set_key) or "0") or 0)
            except Exception:
                existing_dim = 0
            if existing_dim and existing_dim != vector_dim:
                try:
                    client.delete(vector_set_key)
                except Exception:
                    pass
            try:
                client.hset(
                    _index_meta_key(config),
                    mapping={
                        "index_name": config.index_name,
                        "key_prefix": config.key_prefix,
                        "vector_set_key": vector_set_key,
                        "blueprint_id": config.blueprint_id,
                        "embedding_provider": config.embedding_provider,
                        "embedding_model": config.embedding_model,
                        "vector_dim": str(vector_dim),
                        "vector_backend": "redis_vector_set",
                    },
                )
            except Exception:
                pass
            return {
                "status": "vector_set",
                "index_name": config.index_name,
                "vector_set_key": vector_set_key,
                "vector_dim": vector_dim,
                "store": "redis_vector_set",
                "fallback_reason": f"Redis Search index unavailable: {exc}",
            }
        raise RagError(
            "Could not create Redis vector index "
            f"{config.index_name}. Verify Redis 8/RediSearch vector support is enabled and FT.CREATE supports VECTOR fields: {exc}"
        ) from exc
    try:
        client.hset(
            _index_meta_key(config),
            mapping={
                "index_name": config.index_name,
                "key_prefix": config.key_prefix,
                "blueprint_id": config.blueprint_id,
                "embedding_provider": config.embedding_provider,
                "embedding_model": config.embedding_model,
                "vector_dim": str(vector_dim),
                "vector_backend": "redis_search",
            },
        )
    except Exception:
        pass
    return {"status": "created", "index_name": config.index_name, "vector_dim": vector_dim}


def _chunk_record(config: RagConfig, chunk: RagChunk, vector: list[float]) -> dict[str, Any]:
    return {
        "chunk_id": chunk.chunk_id,
        "text": chunk.text,
        "path": chunk.path,
        "heading": chunk.heading,
        "section": chunk.section,
        "blueprint_id": chunk.blueprint_id,
        "source_hash": chunk.source_hash,
        "source_mtime": str(chunk.source_mtime),
        "embedding_model": config.embedding_model,
        "metadata": _json_dumps(chunk.metadata),
        "embedding": vector,
    }


def _redis_record(config: RagConfig, chunk: RagChunk, vector: list[float]) -> dict[str, Any]:
    record = _chunk_record(config, chunk, vector)
    record["embedding"] = _vector_to_bytes(vector)
    return record


def _chunk_from_record(key: str, record: dict[str, Any], score: float) -> RagChunk:
    return RagChunk(
        chunk_id=_decode(record.get("chunk_id")) or key.rsplit(":", 1)[-1],
        text=_decode(record.get("text")),
        path=_decode(record.get("path")),
        heading=_decode(record.get("heading")),
        section=_decode(record.get("section")),
        blueprint_id=_decode(record.get("blueprint_id")),
        source_hash=_decode(record.get("source_hash")),
        source_mtime=float(_decode(record.get("source_mtime")) or 0.0),
        score=float(score),
        key=key,
        metadata=_json_loads(record.get("metadata")),
    )


def index_knowledge_dir(
    knowledge_dir: str | Path,
    config: RagConfig,
    *,
    redis_client: Any | None = None,
    embedder: Any | None = None,
) -> RagIndexSummary:
    root = Path(knowledge_dir).expanduser().resolve()
    chunks = chunk_knowledge_dir(root, config)
    warnings: list[str] = []
    vectors = _embed_texts([chunk.text for chunk in chunks], config, embedder=embedder, input_type="document")
    vector_dim = len(vectors[0]) if vectors else config.vector_dim
    client = redis_client or _connect_redis(config)
    index_info = ensure_index(config, vector_dim=vector_dim, redis_client=client)
    current_keys: set[str] = set()
    if isinstance(client, MemoryRagStore):
        for chunk, vector in zip(chunks, vectors):
            key = f"{config.key_prefix}:{chunk.chunk_id}"
            current_keys.add(key)
            client.upsert(key, _chunk_record(config, chunk, vector))
        stale = [key for key in client.keys(f"{config.key_prefix}:") if key not in current_keys]
        deleted_count = client.delete(*stale)
    elif (index_info or {}).get("store") == "redis_vector_set":
        vector_set_key = str((index_info or {}).get("vector_set_key") or _vector_set_key(config))
        pipeline = client.pipeline()
        for chunk, vector in zip(chunks, vectors):
            key = f"{config.key_prefix}:{chunk.chunk_id}"
            current_keys.add(key)
            pipeline.hset(key, mapping=_redis_record(config, chunk, vector))
            pipeline.execute_command(
                "VADD",
                vector_set_key,
                "VALUES",
                len(vector),
                *vector,
                key,
                "SETATTR",
                _json_dumps(
                    {
                        "chunk_id": chunk.chunk_id,
                        "path": chunk.path,
                        "heading": chunk.heading,
                        "section": chunk.section,
                        "blueprint_id": chunk.blueprint_id,
                        "embedding_model": config.embedding_model,
                    }
                ),
            )
        if chunks:
            pipeline.execute()
        stale = []
        for key in client.scan_iter(f"{config.key_prefix}:*"):
            decoded = _decode(key)
            if decoded == vector_set_key:
                continue
            if decoded not in current_keys:
                stale.append(key)
        deleted_count = 0
        if stale:
            deleted_count = int(client.delete(*stale) or 0)
            try:
                client.execute_command("VREM", vector_set_key, *[_decode(key) for key in stale])
            except Exception:
                pass
    else:
        pipeline = client.pipeline()
        for chunk, vector in zip(chunks, vectors):
            key = f"{config.key_prefix}:{chunk.chunk_id}"
            current_keys.add(key)
            pipeline.hset(key, mapping=_redis_record(config, chunk, vector))
        if chunks:
            pipeline.execute()
        stale = []
        for key in client.scan_iter(f"{config.key_prefix}:*"):
            decoded = _decode(key)
            if decoded not in current_keys:
                stale.append(key)
        deleted_count = int(client.delete(*stale) or 0) if stale else 0
    if not chunks:
        warnings.append("No supported knowledge chunks found to index.")
    return RagIndexSummary(
        blueprint_id=config.blueprint_id,
        namespace=config.namespace or DEFAULT_NAMESPACE,
        knowledge_dir=str(root),
        index_name=config.index_name,
        key_prefix=config.key_prefix,
        embedding_provider=config.embedding_provider,
        embedding_model=config.embedding_model,
        vector_dim=vector_dim,
        indexed_count=len(chunks),
        deleted_count=deleted_count,
        skipped_count=0,
        warnings=warnings,
    )


def _tag_escape(value: str) -> str:
    return re.sub(r"([\\{}\\[\\](),.:;!@#$%^&*\\-+=~|\\\"'<>?/\\s])", r"\\\1", value)


def _query_filter(config: RagConfig, filters: dict[str, Any] | None) -> str:
    parts = [f"@blueprint_id:{{{_tag_escape(config.blueprint_id)}}}"]
    for name in ("path", "section", "embedding_model"):
        value = (filters or {}).get(name)
        if value:
            parts.append(f"@{name}:{{{_tag_escape(str(value))}}}")
    return " ".join(parts) if parts else "*"


def retrieve_knowledge(
    query: str,
    config: RagConfig,
    filters: dict[str, Any] | None = None,
    *,
    redis_client: Any | None = None,
    embedder: Any | None = None,
) -> list[RagChunk]:
    query = str(query or "").strip()
    if not query:
        return []
    query_vector = _embed_texts([query], config, embedder=embedder, input_type="query")[0]
    client = redis_client or _connect_redis(config)
    if isinstance(client, MemoryRagStore):
        return client.query(config, query_vector, config.top_k, filters=filters)
    try:
        from redis.commands.search.query import Query
    except Exception as exc:  # pragma: no cover - depends on optional package
        raise RagError("Install redis with RediSearch command support to run RAG retrieval.") from exc
    index_info = ensure_index(config, vector_dim=len(query_vector), redis_client=client)
    if (index_info or {}).get("store") == "redis_vector_set":
        vector_set_key = str((index_info or {}).get("vector_set_key") or _vector_set_key(config))
        count = config.top_k if not filters else max(config.top_k * 5, config.top_k)
        try:
            response = client.execute_command(
                "VSIM",
                vector_set_key,
                "VALUES",
                len(query_vector),
                *query_vector,
                "WITHSCORES",
                "WITHATTRIBS",
                "COUNT",
                count,
            )
        except Exception as exc:
            raise RagError(
                "Redis vector-set search failed for "
                f"{vector_set_key}. Verify Redis 8 vector-set commands VADD/VSIM are available and vectors match "
                f"dimension {len(query_vector)}: {exc}"
            ) from exc
        chunks: list[RagChunk] = []
        items = list(response or [])
        for offset in range(0, len(items), 3):
            if offset + 2 >= len(items):
                break
            key = _decode(items[offset])
            try:
                score = float(_decode(items[offset + 1]) or 0.0)
            except Exception:
                score = 0.0
            attributes = _json_loads(items[offset + 2])
            if any(str((attributes or {}).get(name) or "") != str(value) for name, value in (filters or {}).items() if value):
                continue
            try:
                record = _decoded_mapping(client.hgetall(key))
            except Exception:
                record = {}
            if not record and isinstance(attributes, dict):
                record = {**attributes, "text": "", "source_mtime": "0", "metadata": "{}"}
            if record:
                chunks.append(_chunk_from_record(key, record, max(0.0, score)))
            if len(chunks) >= config.top_k:
                break
        return chunks
    search_filter = _query_filter(config, filters)
    redis_query = (
        Query(f"({search_filter})=>[KNN {config.top_k} @embedding $query_vector AS vector_score]")
        .sort_by("vector_score")
        .return_fields(
            "vector_score",
            "chunk_id",
            "text",
            "path",
            "heading",
            "section",
            "blueprint_id",
            "source_hash",
            "source_mtime",
            "embedding_model",
            "metadata",
        )
        .paging(0, config.top_k)
        .dialect(2)
    )
    try:
        response = client.ft(config.index_name).search(redis_query, {"query_vector": _vector_to_bytes(query_vector)})
    except Exception as exc:
        raise RagError(
            "Redis KNN vector search failed for "
            f"{config.index_name}. Verify Redis 8 vector search is available, FT.INFO reports the embedding field, "
            f"and stored vectors match dimension {len(query_vector)}: {exc}"
        ) from exc
    chunks: list[RagChunk] = []
    for doc in getattr(response, "docs", []) or []:
        record = {
            "chunk_id": getattr(doc, "chunk_id", ""),
            "text": getattr(doc, "text", ""),
            "path": getattr(doc, "path", ""),
            "heading": getattr(doc, "heading", ""),
            "section": getattr(doc, "section", ""),
            "blueprint_id": getattr(doc, "blueprint_id", ""),
            "source_hash": getattr(doc, "source_hash", ""),
            "source_mtime": getattr(doc, "source_mtime", "0"),
            "metadata": getattr(doc, "metadata", "{}"),
        }
        distance = float(_decode(getattr(doc, "vector_score", "1")) or 1.0)
        chunks.append(_chunk_from_record(str(getattr(doc, "id", "")), record, max(0.0, 1.0 - distance)))
    return chunks


def build_rag_context(
    query: str,
    config: RagConfig,
    max_chars: int = 6000,
    *,
    filters: dict[str, Any] | None = None,
    redis_client: Any | None = None,
    embedder: Any | None = None,
) -> dict[str, Any]:
    chunks = retrieve_knowledge(query, config, filters=filters, redis_client=redis_client, embedder=embedder)
    max_chars = max(500, int(max_chars or 6000))
    context_parts: list[str] = []
    citations: list[dict[str, Any]] = []
    used_chars = 0
    for index, chunk in enumerate(chunks, start=1):
        header = f"[{index}] {chunk.path} :: {chunk.heading} (score={chunk.score:.3f})"
        body = chunk.text.strip()
        entry = f"{header}\n{body}"
        remaining = max_chars - used_chars
        if remaining <= 0:
            break
        if len(entry) > remaining:
            entry = entry[:remaining].rstrip()
        context_parts.append(entry)
        used_chars += len(entry) + 2
        citations.append(
            {
                "ref": index,
                "chunk_id": chunk.chunk_id,
                "path": chunk.path,
                "heading": chunk.heading,
                "section": chunk.section,
                "score": chunk.score,
                "source_hash": chunk.source_hash,
            }
        )
    return {
        "query": query,
        "blueprint_id": config.blueprint_id,
        "namespace": config.namespace,
        "index_name": config.index_name,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "top_k": config.top_k,
        "max_chars": max_chars,
        "context": "\n\n".join(context_parts),
        "chunks": [chunk.to_dict() for chunk in chunks],
        "citations": citations,
    }


def delete_blueprint_index(config: RagConfig, *, redis_client: Any | None = None) -> dict[str, Any]:
    client = redis_client or _connect_redis(config)
    keys_deleted = 0
    index_deleted = False
    meta_deleted = 0
    if isinstance(client, MemoryRagStore):
        keys_deleted = client.delete(*client.keys(f"{config.key_prefix}:"))
        meta_deleted = int(client.delete(_index_meta_key(config)) or 0)
        index_deleted = client.indexes.pop(config.index_name, None) is not None
        return {"index_name": config.index_name, "keys_deleted": keys_deleted, "index_deleted": index_deleted, "meta_deleted": meta_deleted}
    keys = list(client.scan_iter(f"{config.key_prefix}:*"))
    if keys:
        keys_deleted = int(client.delete(*keys) or 0)
    try:
        keys_deleted += int(client.delete(_vector_set_key(config)) or 0)
    except Exception:
        pass
    try:
        meta_deleted = int(client.delete(_index_meta_key(config)) or 0)
    except Exception:
        meta_deleted = 0
    try:
        client.ft(config.index_name).dropindex(delete_documents=False)
        index_deleted = True
    except Exception:
        index_deleted = False
    return {"index_name": config.index_name, "keys_deleted": keys_deleted, "index_deleted": index_deleted, "meta_deleted": meta_deleted}


def knowledge_rag_config(values: dict[str, Any] | None) -> dict[str, Any]:
    source = values or {}
    raw = source.get("knowledge_rag") if isinstance(source.get("knowledge_rag"), dict) else source
    raw = raw if isinstance(raw, dict) else {}
    return {
        "enabled": _as_bool(raw.get("enabled"), True),
        "required": _as_bool(raw.get("required"), False),
        "redis_url": str(raw.get("redis_url") or ""),
        "namespace": str(raw.get("namespace") or ""),
        "embedding_provider": str(raw.get("embedding_provider") or DEFAULT_EMBEDDING_PROVIDER),
        "embedding_model": str(raw.get("embedding_model") or DEFAULT_EMBEDDING_MODEL),
        "embedding_api_base": str(raw.get("embedding_api_base") or DEFAULT_EMBEDDING_API_BASE),
        "embedding_query_prefix": _as_config_string(raw.get("embedding_query_prefix"), DEFAULT_EMBEDDING_QUERY_PREFIX),
        "embedding_document_prefix": _as_config_string(raw.get("embedding_document_prefix"), DEFAULT_EMBEDDING_DOCUMENT_PREFIX),
        "embedding_start_command": _as_config_string(raw.get("embedding_start_command"), DEFAULT_EMBEDDING_START_COMMAND),
        "embedding_healthcheck_enabled": _as_bool(raw.get("embedding_healthcheck_enabled"), True),
        "index_on_startup": _as_bool(raw.get("index_on_startup"), True),
        "top_k": _as_int(raw.get("top_k"), 5),
        "max_context_chars": _as_int(raw.get("max_context_chars"), 6000),
        "chunk_size": _as_int(raw.get("chunk_size"), 220),
        "chunk_overlap": _as_int(raw.get("chunk_overlap"), 40),
        "vector_dim": _as_int(raw.get("vector_dim"), DEFAULT_VECTOR_DIM),
    }


def serializable_rag_config(config: RagConfig) -> dict[str, Any]:
    return {
        "blueprint_id": config.blueprint_id,
        "namespace": config.namespace,
        "index_name": config.index_name,
        "key_prefix": config.key_prefix,
        "embedding_provider": config.embedding_provider,
        "embedding_model": config.embedding_model,
        "embedding_api_base": config.embedding_api_base,
        "embedding_query_prefix": config.embedding_query_prefix,
        "embedding_document_prefix": config.embedding_document_prefix,
        "embedding_start_command": config.embedding_start_command,
        "embedding_healthcheck_enabled": config.embedding_healthcheck_enabled,
        "top_k": config.top_k,
        "vector_dim": config.vector_dim,
        "required": config.required,
    }


def resolve_blueprint_knowledge_dir(
    blueprint_dir: str | Path,
    active_knowledge: dict[str, Any] | None = None,
    configured_path: str | Path | None = None,
) -> Path:
    root = Path(blueprint_dir).expanduser().resolve()
    if configured_path:
        candidate = Path(configured_path).expanduser()
        if not candidate.is_absolute():
            candidate = root / candidate
        return candidate
    resolved = (active_knowledge or {}).get("resolved_path")
    if resolved:
        parent = Path(str(resolved)).expanduser().parent
        if parent.exists():
            return parent
    return root / "knowledge"


def knowledge_rag_warning(message: str, error: str = "") -> dict[str, Any]:
    return {
        "kind": "knowledge_rag",
        "status": "knowledge_rag_failed",
        "message": message,
        "error": error,
    }


def _emit_event(event_callback: Any | None, event_type: str, payload: dict[str, Any]) -> None:
    if event_callback is None:
        return
    try:
        event_callback(event_type, payload)
    except TypeError:
        event_callback({"event": event_type, **payload})


def prepare_blueprint_knowledge_rag(
    *,
    blueprint_id: str,
    blueprint_dir: str | Path,
    config: dict[str, Any] | None = None,
    active_knowledge: dict[str, Any] | None = None,
    knowledge_dir: str | Path | None = None,
    event_callback: Any | None = None,
    redis_client: Any | None = None,
    embedder: Any | None = None,
) -> dict[str, Any]:
    raw = knowledge_rag_config(config)
    state: dict[str, Any] = {
        "enabled": bool(raw.get("enabled")),
        "status": "disabled",
        "warnings": [],
        "config": {
            "namespace": raw.get("namespace"),
            "embedding_provider": raw.get("embedding_provider"),
            "embedding_model": raw.get("embedding_model"),
            "embedding_api_base": raw.get("embedding_api_base"),
            "top_k": raw.get("top_k"),
            "max_context_chars": raw.get("max_context_chars"),
            "index_on_startup": raw.get("index_on_startup"),
            "required": raw.get("required"),
        },
    }
    if not raw.get("enabled"):
        return state
    resolved_knowledge_dir: Path | None = None
    current_manifest: dict[str, Any] = {}
    previous_state: dict[str, Any] = {}
    rag_config: RagConfig | None = None
    try:
        rag_config = RagConfig.from_mapping(raw, blueprint_id=blueprint_id)
        state["_rag_config"] = rag_config
        state["config"].update(serializable_rag_config(rag_config))
        resolved_knowledge_dir = resolve_blueprint_knowledge_dir(
            blueprint_dir,
            active_knowledge=active_knowledge,
            configured_path=knowledge_dir or raw.get("knowledge_dir"),
        )
        state["knowledge_dir"] = str(resolved_knowledge_dir)
        current_manifest = knowledge_manifest(resolved_knowledge_dir)
        previous_state = _previous_rag_state(resolved_knowledge_dir, rag_config, redis_client=redis_client)
        index_changed = (
            not previous_state
            or previous_state.get("status") != "ready"
            or str(previous_state.get("index_manifest_hash") or "") != str(current_manifest.get("index_manifest_hash") or "")
        )
        if raw.get("index_on_startup", True):
            if index_changed:
                indexing_state = _public_state_from_manifest(
                    config=rag_config,
                    current_manifest=current_manifest,
                    previous=previous_state,
                    status="indexing",
                    changed=True,
                    indexed_at=previous_state.get("last_indexed_at") or "",
                    warnings=[],
                    index_summary=previous_state.get("index_summary") if isinstance(previous_state.get("index_summary"), dict) else {},
                )
                indexing_state["files"] = [
                    {**item, "status": "indexing" if item.get("supported") else "unsupported"}
                    for item in indexing_state.get("files") or []
                    if item.get("status") != "removed"
                ]
                _write_local_rag_state(resolved_knowledge_dir, indexing_state)
                _write_redis_rag_state(rag_config, indexing_state, redis_client=redis_client)
                _emit_event(
                    event_callback,
                    "knowledge_rag.indexing",
                    {
                        "tool": "knowledge_rag.index",
                        "status": "indexing",
                        "knowledge_dir": str(resolved_knowledge_dir),
                        "index_name": rag_config.index_name,
                        "manifest_hash": current_manifest.get("manifest_hash"),
                        "index_manifest_hash": current_manifest.get("index_manifest_hash"),
                    },
                )
                if embedder is None and rag_config.embedding_healthcheck_enabled:
                    state["embedding_backend"] = ensure_embedding_backend(rag_config)
                summary = index_knowledge_dir(
                    resolved_knowledge_dir,
                    rag_config,
                    redis_client=redis_client,
                    embedder=embedder,
                )
                summary_dict = summary.to_dict() if hasattr(summary, "to_dict") else dict(summary)
                indexed_at = _utc_now_iso()
                state.update(
                    _public_state_from_manifest(
                        config=rag_config,
                        current_manifest=current_manifest,
                        previous=previous_state,
                        status="ready",
                        changed=True,
                        indexed_at=indexed_at,
                        warnings=list(summary_dict.get("warnings") or []),
                        index_summary=summary_dict,
                    )
                )
                _write_local_rag_state(resolved_knowledge_dir, public_rag_state(state))
                _write_redis_rag_state(rag_config, public_rag_state(state), redis_client=redis_client)
                _emit_event(
                    event_callback,
                    "knowledge_rag.ready",
                    {
                        "tool": "knowledge_rag.index",
                        "status": "ready",
                        "knowledge_dir": state.get("knowledge_dir"),
                        "index_name": state["config"].get("index_name"),
                        "manifest_hash": state.get("manifest_hash"),
                        "indexed_count": summary_dict.get("indexed_count"),
                        "deleted_count": summary_dict.get("deleted_count"),
                    },
                )
            else:
                state.update(
                    _public_state_from_manifest(
                        config=rag_config,
                        current_manifest=current_manifest,
                        previous=previous_state,
                        status="ready",
                        changed=False,
                        indexed_at=previous_state.get("last_indexed_at") or "",
                        warnings=list(previous_state.get("warnings") or []),
                        index_summary=previous_state.get("index_summary") if isinstance(previous_state.get("index_summary"), dict) else {},
                    )
                )
                _emit_event(
                    event_callback,
                    "knowledge_rag.skipped_unchanged",
                    {
                        "tool": "knowledge_rag.index",
                        "status": "skipped_unchanged",
                        "knowledge_dir": state.get("knowledge_dir"),
                        "index_name": state["config"].get("index_name"),
                        "manifest_hash": state.get("manifest_hash"),
                    },
                )
        else:
            state.update(
                _public_state_from_manifest(
                    config=rag_config,
                    current_manifest=current_manifest,
                    previous=previous_state,
                    status="ready",
                    changed=False,
                    indexed_at=previous_state.get("last_indexed_at") or "",
                    warnings=list(previous_state.get("warnings") or []),
                    index_summary=previous_state.get("index_summary") if isinstance(previous_state.get("index_summary"), dict) else {},
                )
            )
        _emit_event(
            event_callback,
            "tool_call_completed",
            {
                "tool": "knowledge_rag.index",
                "status": state.get("status"),
                "changed": state.get("changed"),
                "knowledge_dir": state.get("knowledge_dir"),
                "index_name": state["config"].get("index_name"),
            },
        )
    except Exception as exc:
        warning = knowledge_rag_warning(
            "Knowledge RAG was enabled but Redis/vector indexing could not complete; no static playbook fallback was injected.",
            str(exc),
        )
        state["status"] = "knowledge_rag_failed"
        state["warnings"].append(warning)
        if rag_config is not None and current_manifest:
            state.update(
                _public_state_from_manifest(
                    config=rag_config,
                    current_manifest=current_manifest,
                    previous=previous_state,
                    status="knowledge_rag_failed",
                    changed=True,
                    indexed_at=previous_state.get("last_indexed_at") or "",
                    warnings=[warning],
                    index_summary=previous_state.get("index_summary") if isinstance(previous_state.get("index_summary"), dict) else {},
                )
            )
            state["_rag_config"] = rag_config
            if resolved_knowledge_dir is not None:
                _write_local_rag_state(resolved_knowledge_dir, public_rag_state(state))
                _write_redis_rag_state(rag_config, public_rag_state(state), redis_client=redis_client)
        _emit_event(
            event_callback,
            "knowledge_rag.failed",
            {"tool": "knowledge_rag.index", "status": "knowledge_rag_failed", "error": str(exc)},
        )
        _emit_event(
            event_callback,
            "tool_call_failed",
            {"tool": "knowledge_rag.index", "status": "knowledge_rag_failed", "error": str(exc)},
        )
    return state


def public_rag_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return {"enabled": False, "status": "disabled"}
    return {key: value for key, value in state.items() if not key.startswith("_")}


def knowledge_rag_required(state: dict[str, Any] | None) -> bool:
    if not state or not state.get("enabled"):
        return False
    config = state.get("config") if isinstance(state.get("config"), dict) else {}
    return _as_bool(state.get("required"), False) or _as_bool(config.get("required"), False)


def require_ready_knowledge_rag(
    state: dict[str, Any] | None,
    *,
    stage: str = "",
    company: str = "",
    context: dict[str, Any] | None = None,
    min_citations: int = 0,
) -> dict[str, Any] | None:
    if not knowledge_rag_required(state):
        return context if context is not None else state
    status = (state or {}).get("status") or "disabled"
    label_parts = [part for part in [stage, company] if part]
    label = f" for {' / '.join(label_parts)}" if label_parts else ""
    if status != "ready":
        warnings = (state or {}).get("warnings") or []
        detail = ""
        if warnings and isinstance(warnings[0], dict):
            detail = str(warnings[0].get("error") or warnings[0].get("message") or "")
        raise RagError(f"Knowledge RAG is required but not ready{label}: status={status}{f' ({detail})' if detail else ''}")
    if context is not None and int(min_citations or 0) > 0:
        citations = context.get("citations") or []
        if len(citations) < int(min_citations):
            raise RagError(
                "Knowledge RAG is required but retrieval returned "
                f"{len(citations)} citation(s){label}; expected at least {int(min_citations)}."
            )
    return context if context is not None else state


def retrieve_knowledge_rag_context(
    *,
    knowledge_rag: dict[str, Any] | None,
    query: str,
    stage: str = "",
    company: str = "",
    filters: dict[str, Any] | None = None,
    redis_client: Any | None = None,
    embedder: Any | None = None,
) -> dict[str, Any]:
    if not knowledge_rag or not knowledge_rag.get("enabled"):
        return {"enabled": False, "status": "disabled", "query": query, "context": "", "citations": [], "chunks": []}
    if knowledge_rag.get("status") != "ready" or not knowledge_rag.get("_rag_config"):
        return {
            "enabled": True,
            "status": knowledge_rag.get("status") or "knowledge_rag_failed",
            "query": query,
            "context": "",
            "citations": [],
            "chunks": [],
            "warnings": list(knowledge_rag.get("warnings") or []),
            "stage": stage,
            "company": company,
        }
    try:
        context = build_rag_context(
            query,
            knowledge_rag["_rag_config"],
            max_chars=int((knowledge_rag.get("config") or {}).get("max_context_chars") or 6000),
            filters=filters,
            redis_client=redis_client,
            embedder=embedder,
        )
        context["enabled"] = True
        context["status"] = "ready"
        context["stage"] = stage
        context["company"] = company
        return context
    except Exception as exc:
        warning = knowledge_rag_warning(
            f"Knowledge RAG retrieval failed for {stage or 'prompt'}; prompt continued without retrieved knowledge context.",
            str(exc),
        )
        knowledge_rag.setdefault("warnings", []).append(warning)
        return {
            "enabled": True,
            "status": "knowledge_rag_failed",
            "query": query,
            "context": "",
            "citations": [],
            "chunks": [],
            "warnings": [warning],
            "stage": stage,
            "company": company,
        }


def delete_blueprint_knowledge_rag(
    blueprint_id: str,
    config: dict[str, Any] | RagConfig | None = None,
    *,
    redis_client: Any | None = None,
) -> dict[str, Any]:
    rag_config = config if isinstance(config, RagConfig) else RagConfig.from_mapping(knowledge_rag_config(config), blueprint_id=blueprint_id)
    result = delete_blueprint_index(rag_config, redis_client=redis_client)
    result["blueprint_id"] = rag_config.blueprint_id
    result["namespace"] = rag_config.namespace
    result["key_prefix"] = rag_config.key_prefix
    return result
