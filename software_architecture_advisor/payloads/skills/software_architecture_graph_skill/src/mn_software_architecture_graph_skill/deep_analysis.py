"""Deterministic, read-only evidence fusion for software architecture reviews."""

from __future__ import annotations

import ast
import hashlib
import json
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from .analysis import analyze_graph


_ENTRYPOINT_NAMES = {
    "app.py", "application.py", "cli.py", "index.js", "index.ts", "main.c",
    "main.cpp", "main.go", "main.java", "main.kt", "main.py", "main.rs",
    "manage.py", "server.js", "server.py", "server.ts", "worker.py",
}
_METADATA_NAMES = {
    "agents.md", "cargo.lock", "cargo.toml", "docker-compose.yml",
    "docker-compose.yaml", "dockerfile", "go.mod", "go.sum", "makefile",
    "package-lock.json", "package.json", "pnpm-lock.yaml", "pom.xml",
    "pyproject.toml", "readme", "readme.md", "requirements.txt",
    "tsconfig.json", "yarn.lock",
}
_METADATA_SUFFIXES = {
    ".gradle", ".hcl", ".json", ".lock", ".md", ".properties", ".sql",
    ".tf", ".toml", ".xml", ".yaml", ".yml",
}
_TEST_PATH_RE = re.compile(
    r"(?:^|/)(?:tests?|specs?)(?:/|$)|(?:^|/)(?:test_[^/]+|[^/]+_(?:test|spec))\.[^.]+$|\.(?:test|spec)\.[^.]+$",
    re.IGNORECASE,
)
_GENERIC_SYMBOL_PATTERNS = {
    "class": re.compile(r"^\s*(?:export\s+)?(?:public\s+)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)", re.MULTILINE),
    "interface": re.compile(r"^\s*(?:export\s+)?(?:public\s+)?(?:interface|trait)\s+([A-Za-z_$][\w$]*)", re.MULTILINE),
    "function": re.compile(r"^\s*(?:export\s+)?(?:public\s+|private\s+|protected\s+|static\s+|async\s+)*(?:function|func|fn)\s+([A-Za-z_$][\w$]*)", re.MULTILINE),
}
_ENDPOINT_RE = re.compile(
    r"(?:@(?:app|router)\.(?:get|post|put|patch|delete)|\b(?:GET|POST|PUT|PATCH|DELETE)\s+/|\b(?:get|post|put|patch|delete)\s*\(\s*['\"][/])",
    re.IGNORECASE,
)
_INGRESS_PATTERNS = {
    "http_endpoint": _ENDPOINT_RE,
    "command_line": re.compile(r"\b(?:sys\.argv|argparse|process\.argv|os\.Args)\b"),
    "message_consumer": re.compile(r"\b(?:consume|consumer|subscribe|handler|on_message)\b", re.IGNORECASE),
}
_PRIVILEGED_PATTERNS = {
    "process_execution": re.compile(r"\b(?:subprocess\.|os\.system\s*\(|Runtime\.getRuntime|ProcessBuilder|child_process\.|exec\s*\()"),
    "dynamic_evaluation": re.compile(r"\b(?:eval|exec)\s*\("),
    "filesystem_write": re.compile(r"\b(?:write_text|write_bytes|open\s*\([^\n]+['\"](?:w|a|x)b?['\"]|FileOutputStream)"),
    "database_mutation": re.compile(r"\b(?:insert|update|delete|save|commit|execute)\s*\(", re.IGNORECASE),
}
_TECH_SIGNATURES = {
    "frameworks": {
        "django": ("django",), "fastapi": ("fastapi",), "flask": ("flask",),
        "spring": ("springframework", "spring boot"), "react": ("react",),
        "nextjs": ("next/", "next.js"), "express": ("express",),
        "rails": ("rails", "active_record"), "aspnet": ("asp.net", "microsoft.aspnetcore"),
    },
    "data_stores": {
        "postgres": ("postgres", "psycopg", "asyncpg", "pgx"),
        "mysql": ("mysql", "pymysql"), "sqlite": ("sqlite",),
        "redis": ("redis",), "mongodb": ("mongodb", "pymongo", "mongoose"),
        "object_storage": ("s3", "blob storage", "google.cloud.storage"),
    },
    "queues": {
        "kafka": ("kafka",), "rabbitmq": ("rabbitmq", "pika", "amqp"),
        "celery": ("celery",), "sqs": ("sqs",),
        "redis_queue": ("import rq", "from rq", "bullmq"),
    },
}


def build_deep_evidence(
    root: str | Path,
    inventory: dict[str, Any],
    graph: dict[str, Any],
    settings: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a bounded fact database and architecture evidence models."""
    settings = settings or {}
    base = Path(root).expanduser().resolve()
    metadata = _metadata_records(base, settings)
    symbol_index = _build_symbol_index(inventory, settings)
    metrics = analyze_graph(
        graph,
        large_module_line_threshold=int(settings.get("large_module_line_threshold", 500)),
    )
    repository_profile = _repository_profile(inventory, graph, metadata, symbol_index)
    test_architecture = _test_architecture(graph, symbol_index)
    state_model = _state_model(inventory)
    trust_model = _trust_model(inventory, symbol_index)
    deployment_model = _deployment_model(metadata)
    history = _history_evidence(metadata, settings)
    hotspots = _structural_hotspots(
        graph, metrics, symbol_index, test_architecture, history, settings
    )
    facts = _fact_database(
        repository_profile=repository_profile,
        metrics=metrics,
        symbol_index=symbol_index,
        state_model=state_model,
        trust_model=trust_model,
        test_architecture=test_architecture,
        deployment_model=deployment_model,
        history=history,
        hotspots=hotspots,
        max_facts=int(settings.get("max_facts", 5000)),
    )
    metrics = {
        **metrics,
        "symbol_count": symbol_index["symbol_count"],
        "endpoint_count": symbol_index["endpoint_count"],
        "state_store_count": len(state_model["stores"]),
        "trust_boundary_candidate_count": len(trust_model["candidate_crossings"]),
        "test_file_count": test_architecture["test_file_count"],
        "direct_test_gap_count": len(test_architecture["direct_test_gaps"]),
        "deployment_descriptor_count": len(deployment_model["descriptors"]),
        "history_available": history["available"],
        "structural_hotspots": hotspots,
    }
    reconstruction = _deterministic_reconstruction(
        repository_profile, graph, state_model, trust_model, deployment_model, history
    )
    return {
        "schema_version": "mn.architecture.deep_evidence.v1",
        "repository_profile": repository_profile,
        "symbol_index": symbol_index,
        "metrics": metrics,
        "state_model": state_model,
        "trust_model": trust_model,
        "test_architecture": test_architecture,
        "deployment_model": deployment_model,
        "history": history,
        "hotspots": hotspots,
        "facts": facts,
        "deterministic_reconstruction": reconstruction,
        "evidence_availability": {
            "source_inventory": "available",
            "syntax_symbols": "available",
            "dependency_graph": "available",
            "test_execution": "not_executed",
            "runtime_traces": "not_supplied",
            "git_history": "available" if history["available"] else "not_supplied",
            "compiler_semantics": "not_executed",
            "security_analyzers": "not_executed",
        },
        "limitations": [
            "Syntax, state, trust, test, and deployment models are deterministic static heuristics, not runtime proof.",
            "Git conclusions require a pre-staged git_history.json evidence file; repository commands are never executed.",
            "Compiler, type checker, test, security scanner, and profiler evidence is reported as unavailable unless separately staged.",
        ],
    }


def compact_inventory(inventory: dict[str, Any]) -> dict[str, Any]:
    """Remove source bodies before durable workflow persistence."""
    compact = {key: value for key, value in inventory.items() if key != "files"}
    compact["files"] = [
        {key: value for key, value in item.items() if key != "text"}
        for item in inventory.get("files") or []
    ]
    return compact


def _metadata_records(base: Path, settings: dict[str, Any]) -> list[dict[str, Any]]:
    max_files = int(settings.get("max_metadata_files", 500))
    max_bytes = int(settings.get("max_metadata_file_bytes", 524_288))
    excluded = set(settings.get("excluded_directories") or []) | {
        ".git", ".venv", "build", "coverage", "dist", "node_modules", "target", "vendor", "venv",
    }
    records: list[dict[str, Any]] = []
    for directory, dir_names, file_names in os.walk(base, topdown=True, followlinks=False):
        dir_names[:] = sorted(name for name in dir_names if name not in excluded)
        for name in sorted(file_names):
            path = Path(directory) / name
            rel = path.relative_to(base).as_posix()
            lowered = name.lower()
            if not (
                lowered in _METADATA_NAMES
                or path.suffix.lower() in _METADATA_SUFFIXES
                or rel.startswith(".github/workflows/")
                or "/adr" in f"/{rel.lower()}"
            ):
                continue
            try:
                if path.stat().st_size > max_bytes:
                    continue
                data = path.read_bytes()
            except OSError:
                continue
            if b"\x00" in data[:4096]:
                continue
            text = data.decode("utf-8", errors="replace")
            records.append({
                "path": rel,
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "kind": _metadata_kind(rel),
                "_text": text,
            })
            if len(records) >= max_files:
                return records
    return records


def _metadata_kind(path: str) -> str:
    lowered = path.lower()
    name = Path(lowered).name
    if name == "dockerfile" or "docker-compose" in name or "k8s" in lowered or "kubernetes" in lowered:
        return "deployment"
    if lowered.startswith(".github/workflows/"):
        return "ci"
    if name in {"pyproject.toml", "package.json", "cargo.toml", "go.mod", "pom.xml"} or name.endswith(".gradle"):
        return "language_manifest"
    if "readme" in name or "/adr" in f"/{lowered}" or "architecture" in name:
        return "documentation"
    if path.endswith((".tf", ".hcl")):
        return "infrastructure"
    if path.endswith((".sql",)) or "migration" in lowered:
        return "migration"
    return "configuration"


class _PythonSymbolVisitor(ast.NodeVisitor):
    def __init__(self, path: str, module: str) -> None:
        self.path = path
        self.module = module
        self.scope: list[str] = []
        self.symbols: list[dict[str, Any]] = []
        self.calls: list[dict[str, Any]] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self._add_symbol(node, "class")
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node, "function")

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, "async_function")

    def visit_Call(self, node: ast.Call) -> None:
        self.calls.append({
            "path": self.path,
            "line": int(getattr(node, "lineno", 0) or 0),
            "caller": ".".join([self.module, *self.scope]),
            "callee": _python_name(node.func),
        })
        self.generic_visit(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, kind: str) -> None:
        self._add_symbol(node, kind, complexity=_python_complexity(node))
        self.scope.append(node.name)
        self.generic_visit(node)
        self.scope.pop()

    def _add_symbol(self, node: Any, kind: str, complexity: int | None = None) -> None:
        decorators = [_python_name(item) for item in getattr(node, "decorator_list", [])]
        symbol = {
            "symbol_id": ".".join([self.module, *self.scope, node.name]),
            "name": node.name,
            "qualified_name": ".".join([*self.scope, node.name]),
            "kind": kind,
            "path": self.path,
            "line": int(getattr(node, "lineno", 0) or 0),
            "decorators": [item for item in decorators if item],
        }
        if complexity is not None:
            symbol["cyclomatic_complexity"] = complexity
        self.symbols.append(symbol)


def _build_symbol_index(inventory: dict[str, Any], settings: dict[str, Any]) -> dict[str, Any]:
    max_symbols = int(settings.get("max_symbols", 20_000))
    max_calls = int(settings.get("max_call_sites", 20_000))
    symbols: list[dict[str, Any]] = []
    calls: list[dict[str, Any]] = []
    parse_failures: list[dict[str, str]] = []
    endpoints: list[dict[str, Any]] = []
    for item in inventory.get("files") or []:
        text = item.get("text") or ""
        path = item["path"]
        if item.get("extension") == ".py":
            try:
                tree = ast.parse(text)
            except SyntaxError as exc:
                parse_failures.append({"path": path, "reason": f"python_syntax_error:{exc.lineno or 0}"})
            else:
                visitor = _PythonSymbolVisitor(path, item["module_id"])
                visitor.visit(tree)
                symbols.extend(visitor.symbols)
                calls.extend(visitor.calls)
                for symbol in visitor.symbols:
                    decorators = " ".join(symbol.get("decorators") or []).lower()
                    if any(marker in decorators for marker in (".get", ".post", ".put", ".patch", ".delete", "route")):
                        endpoints.append({"path": path, "line": symbol["line"], "symbol_id": symbol["symbol_id"], "kind": "decorated_endpoint"})
        else:
            for kind, pattern in _GENERIC_SYMBOL_PATTERNS.items():
                for match in pattern.finditer(text):
                    symbols.append({
                        "symbol_id": f"{item['module_id']}.{match.group(1)}",
                        "name": match.group(1),
                        "qualified_name": match.group(1),
                        "kind": kind,
                        "path": path,
                        "line": text.count("\n", 0, match.start()) + 1,
                        "decorators": [],
                    })
        for match in _ENDPOINT_RE.finditer(text):
            endpoints.append({"path": path, "line": text.count("\n", 0, match.start()) + 1, "kind": "endpoint_pattern"})
    symbols = sorted(symbols, key=lambda item: (item["path"], item["line"], item["symbol_id"]))[:max_symbols]
    calls = sorted(calls, key=lambda item: (item["path"], item["line"], item["callee"]))[:max_calls]
    endpoints = list({(item["path"], item["line"], item["kind"]): item for item in endpoints}.values())
    counts = Counter(item["kind"] for item in symbols)
    return {
        "schema_version": "mn.architecture.symbol_index.v1",
        "symbol_count": len(symbols),
        "call_site_count": len(calls),
        "endpoint_count": len(endpoints),
        "symbol_kind_counts": dict(sorted(counts.items())),
        "symbols": symbols,
        "call_sites": calls,
        "endpoints": endpoints[:2000],
        "parse_failures": parse_failures[:500],
        "truncated": len(symbols) >= max_symbols or len(calls) >= max_calls,
        "limitations": [
            "Python symbols use the standard-library AST; other languages use bounded declaration patterns.",
            "Call sites are syntactic and do not resolve dynamic dispatch or concrete receiver types.",
        ],
    }


def _python_name(node: Any) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _python_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    if isinstance(node, ast.Call):
        return _python_name(node.func)
    return ""


def _python_complexity(node: ast.AST) -> int:
    score = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While, ast.IfExp, ast.ExceptHandler, ast.With, ast.AsyncWith, ast.comprehension)):
            score += 1
        elif isinstance(child, ast.BoolOp):
            score += max(1, len(child.values) - 1)
        elif isinstance(child, ast.Match):
            score += len(child.cases)
    return score


def _repository_profile(
    inventory: dict[str, Any],
    graph: dict[str, Any],
    metadata: list[dict[str, Any]],
    symbol_index: dict[str, Any],
) -> dict[str, Any]:
    files = inventory.get("files") or []
    total_bytes = max(1, int(inventory.get("source_bytes") or 0))
    bytes_by_language: Counter[str] = Counter()
    package_counts: Counter[str] = Counter()
    entrypoints: list[dict[str, Any]] = []
    corpus = "\n".join(str(item.get("text") or "")[:200_000].lower() for item in files)
    for item in files:
        language = _language_name(item.get("extension") or "")
        bytes_by_language[language] += int(item.get("bytes") or 0)
        package_counts[item.get("package") or "root"] += 1
        name = Path(item["path"]).name.lower()
        if name in _ENTRYPOINT_NAMES or "if __name__ ==" in (item.get("text") or ""):
            entrypoints.append({"path": item["path"], "kind": "entrypoint_candidate"})
    technologies = {
        category: sorted(
            name for name, signatures in choices.items()
            if any(signature in corpus for signature in signatures)
        )
        for category, choices in _TECH_SIGNATURES.items()
    }
    language_distribution = {
        name: {
            "bytes": count,
            "fraction": round(count / total_bytes, 4),
        }
        for name, count in sorted(bytes_by_language.items(), key=lambda item: (-item[1], item[0]))
    }
    public_metadata = [{key: value for key, value in item.items() if key != "_text"} for item in metadata]
    documentation_observations = _documentation_observations(metadata)
    return {
        "schema_version": "mn.architecture.repository_profile.v1",
        "languages": language_distribution,
        "packages": [{"name": name, "source_file_count": count} for name, count in package_counts.most_common(100)],
        "applications": [name for name, count in package_counts.most_common(50) if name != "root" and count >= 2],
        "entrypoints": entrypoints[:500],
        "frameworks": technologies["frameworks"],
        "data_stores": technologies["data_stores"],
        "queues": technologies["queues"],
        "metadata_files": public_metadata,
        "architecture_documents": [item["path"] for item in metadata if item["kind"] == "documentation"],
        "documentation_observations": documentation_observations,
        "ci_files": [item["path"] for item in metadata if item["kind"] == "ci"],
        "source_file_count": inventory.get("source_file_count", 0),
        "symbol_count": symbol_index.get("symbol_count", 0),
        "internal_dependency_count": len(graph.get("edges") or []),
    }


def _documentation_observations(metadata: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers = re.compile(
        r"\b(intentional|temporary|source of truth|authorit|cache|legacy|deprecated|architecture|boundary|circular|cycle|coupling|non-deployable|not a deployable)\b",
        re.IGNORECASE,
    )
    observations: list[dict[str, Any]] = []
    for item in metadata:
        if item.get("kind") != "documentation":
            continue
        for line_number, raw_line in enumerate((item.get("_text") or "").splitlines(), start=1):
            text = " ".join(raw_line.strip().split())
            if not text or not markers.search(text):
                continue
            matched_markers = sorted({match.group(0).lower() for match in markers.finditer(text)})
            observations.append({
                "path": item["path"],
                "line": line_number,
                "line_sha256": hashlib.sha256(raw_line.encode("utf-8", errors="replace")).hexdigest(),
                "matched_markers": matched_markers,
                "status": "potential_context_or_counter_evidence",
            })
            if len(observations) >= 200:
                return observations
    return observations


def _language_name(extension: str) -> str:
    return {
        ".py": "python", ".js": "javascript", ".jsx": "javascript",
        ".ts": "typescript", ".tsx": "typescript", ".java": "java",
        ".go": "go", ".rs": "rust", ".c": "c", ".h": "c_cpp",
        ".cpp": "c_cpp", ".hpp": "c_cpp", ".cs": "csharp",
        ".kt": "kotlin", ".kts": "kotlin", ".rb": "ruby", ".php": "php",
        ".swift": "swift",
    }.get(extension, extension.removeprefix(".") or "unknown")


def _state_model(inventory: dict[str, Any]) -> dict[str, Any]:
    signatures = {
        **_TECH_SIGNATURES["data_stores"],
        **_TECH_SIGNATURES["queues"],
        "filesystem": ("open(", "read_text(", "write_text(", "readfile", "writefile"),
        "environment": ("os.getenv", "os.environ", "process.env", "system.getenv"),
    }
    stores: list[dict[str, Any]] = []
    for store, markers in signatures.items():
        readers: set[str] = set()
        writers: set[str] = set()
        references: set[str] = set()
        for item in inventory.get("files") or []:
            lowered = (item.get("text") or "").lower()
            if not any(marker.lower() in lowered for marker in markers):
                continue
            path = item["path"]
            references.add(path)
            if any(token in lowered for token in ("get(", "read", "select", "find", "load", "consume", "fetch")):
                readers.add(path)
            if any(token in lowered for token in ("set(", "write", "insert", "update", "delete", "save", "commit", "publish", "produce", "enqueue")):
                writers.add(path)
        if references:
            stores.append({
                "state_id": f"state:{store}",
                "technology": store,
                "references": sorted(references),
                "readers": sorted(readers),
                "writers": sorted(writers),
                "durability": "unknown",
                "authority": "not_determined",
            })
    ownership_candidates = [
        {
            "state_id": item["state_id"],
            "reason": "multiple_static_writer_candidates",
            "writers": item["writers"],
            "confidence": "low",
        }
        for item in stores if len(item["writers"]) > 1
    ]
    return {
        "schema_version": "mn.architecture.state_model.v1",
        "stores": stores,
        "ownership_candidates": ownership_candidates,
        "limitations": [
            "Reader and writer roles are token-based candidates and require source verification.",
            "Durability and source-of-truth authority cannot be established without runtime/configuration evidence.",
        ],
    }


def _trust_model(inventory: dict[str, Any], symbol_index: dict[str, Any]) -> dict[str, Any]:
    signals: list[dict[str, Any]] = []
    crossings: list[dict[str, Any]] = []
    for item in inventory.get("files") or []:
        text = item.get("text") or ""
        ingress = [name for name, pattern in _INGRESS_PATTERNS.items() if pattern.search(text)]
        sinks = [name for name, pattern in _PRIVILEGED_PATTERNS.items() if pattern.search(text)]
        for name in ingress:
            signals.append({"path": item["path"], "direction": "ingress", "capability": name})
        for name in sinks:
            signals.append({"path": item["path"], "direction": "privileged_sink", "capability": name})
        if ingress and sinks:
            crossings.append({
                "path": item["path"],
                "ingress_signals": ingress,
                "privileged_sink_signals": sinks,
                "status": "candidate_requires_data_flow_verification",
                "confidence": "low",
            })
    return {
        "schema_version": "mn.architecture.trust_model.v1",
        "signals": signals[:5000],
        "candidate_crossings": crossings[:1000],
        "endpoint_count": symbol_index.get("endpoint_count", 0),
        "limitations": [
            "Co-location of ingress and a privileged sink is not proof of data flow or exploitability.",
            "Authentication, authorization, sanitization, and deployment privileges require dedicated verification.",
        ],
    }


def _test_architecture(graph: dict[str, Any], symbol_index: dict[str, Any]) -> dict[str, Any]:
    nodes = graph.get("nodes") or []
    test_modules = {node["module_id"] for node in nodes if _is_test_path(node.get("path") or "")}
    protected: defaultdict[str, set[str]] = defaultdict(set)
    for edge in graph.get("edges") or []:
        if edge.get("from") in test_modules and edge.get("to") not in test_modules:
            protected[edge["to"]].add(edge["from"])
    fan: Counter[str] = Counter()
    for edge in graph.get("edges") or []:
        fan[edge["from"]] += 1
        fan[edge["to"]] += 1
    gaps = [
        {
            "module": node["module_id"],
            "path": node.get("path"),
            "dependency_degree": fan[node["module_id"]],
            "reason": "no_direct_static_test_import",
        }
        for node in nodes
        if node["module_id"] not in test_modules
        and node["module_id"] not in protected
        and fan[node["module_id"]] > 0
    ]
    gaps.sort(key=lambda item: (-item["dependency_degree"], item["module"]))
    return {
        "schema_version": "mn.architecture.test_architecture.v1",
        "test_file_count": len(test_modules),
        "test_modules": sorted(test_modules),
        "direct_test_links": [
            {"source_module": module, "test_modules": sorted(tests)}
            for module, tests in sorted(protected.items())
        ],
        "direct_test_gaps": gaps[:200],
        "test_execution": "forbidden",
        "coverage": "not_measured",
        "mutation_testing": "not_run",
        "limitations": [
            "A missing direct import does not prove missing integration, generated, or black-box coverage.",
            "Tests are inventoried but never executed by this advisory workflow.",
        ],
    }


def _deployment_model(metadata: list[dict[str, Any]]) -> dict[str, Any]:
    descriptors = [
        {key: value for key, value in item.items() if key != "_text"}
        for item in metadata if item["kind"] in {"deployment", "infrastructure", "ci"}
    ]
    units: set[str] = set()
    for item in metadata:
        if item["kind"] not in {"deployment", "infrastructure"}:
            continue
        text = item.get("_text") or ""
        for match in re.finditer(r"^\s{0,4}([A-Za-z][\w.-]+):\s*$", text, re.MULTILINE):
            name = match.group(1)
            if name not in {"services", "volumes", "networks", "environment", "ports", "depends_on"}:
                units.add(name)
    return {
        "schema_version": "mn.architecture.deployment_model.v1",
        "descriptors": descriptors,
        "candidate_units": sorted(units)[:500],
        "runtime_topology": "not_observed",
        "limitations": [
            "Deployment descriptors indicate declared topology, not the currently running production topology.",
            "No deployment command, compose expansion, or infrastructure evaluation is performed.",
        ],
    }


def _history_evidence(metadata: list[dict[str, Any]], settings: dict[str, Any]) -> dict[str, Any]:
    candidates = settings.get("history_evidence_files") or ["architecture_git_history.json", "git_history.json"]
    wanted = {str(item).lower() for item in candidates}
    record = next((item for item in metadata if Path(item["path"]).name.lower() in wanted), None)
    if not record:
        return {
            "schema_version": "mn.architecture.history_evidence.v1",
            "available": False,
            "source": None,
            "file_churn": [],
            "cochange": [],
            "ownership": [],
            "reason": "No pre-staged git history evidence file was supplied; Git commands are not executed.",
        }
    try:
        decoded = json.loads(record.get("_text") or "{}")
    except json.JSONDecodeError:
        return {
            "schema_version": "mn.architecture.history_evidence.v1",
            "available": False,
            "source": record["path"],
            "file_churn": [],
            "cochange": [],
            "ownership": [],
            "reason": "The pre-staged history evidence file was not valid JSON.",
        }
    file_churn = decoded.get("file_churn") or decoded.get("files") or []
    cochange = decoded.get("cochange") or decoded.get("temporal_coupling") or []
    ownership = decoded.get("ownership") or []
    return {
        "schema_version": "mn.architecture.history_evidence.v1",
        "available": True,
        "source": record["path"],
        "file_churn": [item for item in file_churn if isinstance(item, dict)][:5000],
        "cochange": [item for item in cochange if isinstance(item, dict)][:5000],
        "ownership": [item for item in ownership if isinstance(item, dict)][:5000],
        "reason": None,
    }


def _structural_hotspots(
    graph: dict[str, Any],
    metrics: dict[str, Any],
    symbol_index: dict[str, Any],
    tests: dict[str, Any],
    history: dict[str, Any],
    settings: dict[str, Any],
) -> list[dict[str, Any]]:
    fan_in = {item["module"]: int(item["count"]) for item in metrics.get("top_fan_in") or []}
    fan_out = {item["module"]: int(item["count"]) for item in metrics.get("top_fan_out") or []}
    max_degree = max([1, *fan_in.values(), *fan_out.values()])
    complexity: defaultdict[str, int] = defaultdict(int)
    for symbol in symbol_index.get("symbols") or []:
        if "cyclomatic_complexity" in symbol:
            module = next((node["module_id"] for node in graph.get("nodes") or [] if node.get("path") == symbol.get("path")), "")
            if module:
                complexity[module] += int(symbol["cyclomatic_complexity"])
    max_complexity = max([1, *complexity.values()])
    gap_modules = {item["module"] for item in tests.get("direct_test_gaps") or []}
    churn_by_path: dict[str, float] = {}
    for item in history.get("file_churn") or []:
        path = str(item.get("path") or item.get("file") or "")
        raw = item.get("commits") or item.get("change_count") or item.get("churn") or 0
        try:
            churn_by_path[path] = float(raw)
        except (TypeError, ValueError):
            continue
    max_churn = max([1.0, *churn_by_path.values()])
    hotspots: list[dict[str, Any]] = []
    for node in graph.get("nodes") or []:
        module = node["module_id"]
        path = node.get("path") or module
        centrality = round(10 * (fan_in.get(module, 0) + fan_out.get(module, 0)) / (2 * max_degree), 2)
        complexity_score = round(10 * complexity.get(module, 0) / max_complexity, 2)
        test_gap = 8.0 if module in gap_modules else 2.0
        churn_value = churn_by_path.get(path)
        churn_score = round(10 * churn_value / max_churn, 2) if churn_value is not None else None
        components = [centrality, complexity_score, test_gap]
        weights = [0.4, 0.35, 0.25]
        if churn_score is not None:
            components.append(churn_score)
            weights = [0.3, 0.25, 0.2, 0.25]
        score = round(sum(value * weight for value, weight in zip(components, weights)), 2)
        hotspots.append({
            "module": module,
            "path": path,
            "risk_proxy_score": score,
            "components": {
                "dependency_centrality": centrality,
                "static_complexity": complexity_score,
                "direct_test_gap": test_gap,
                "git_churn": churn_score,
            },
            "history_available": churn_score is not None,
        })
    hotspots.sort(key=lambda item: (-item["risk_proxy_score"], item["module"]))
    return hotspots[: int(settings.get("max_hotspots", 50))]


def _fact_database(**values: Any) -> dict[str, Any]:
    max_facts = int(values.pop("max_facts"))
    facts: list[dict[str, Any]] = []

    def add(fact_type: str, evidence_type: str, paths: list[str], value: Any, confidence: str = "high") -> None:
        if len(facts) >= max_facts:
            return
        facts.append({
            "fact_id": f"F{len(facts) + 1:05d}",
            "fact_type": fact_type,
            "evidence_type": evidence_type,
            "tool": "mn-software-architecture-graph-skill",
            "paths": sorted(set(path for path in paths if path)),
            "value": value,
            "confidence": confidence,
        })

    profile = values["repository_profile"]
    for language, measurement in profile.get("languages", {}).items():
        add("language_distribution", "repository_inventory", [], {"language": language, **measurement})
    for item in profile.get("metadata_files") or []:
        add("repository_descriptor", "repository_metadata", [item["path"]], {"kind": item["kind"]})
    metrics = values["metrics"]
    for cycle in metrics.get("cycles") or []:
        add("dependency_cycle", "dependency_graph", [item["path"] for item in cycle], {"modules": [item["module"] for item in cycle]})
    for item in metrics.get("large_modules") or []:
        add("large_module", "source_metric", [item["path"]], {"module": item["module"], "lines": item["lines"]})
    for endpoint in values["symbol_index"].get("endpoints") or []:
        add("endpoint_candidate", "syntax_symbol", [endpoint["path"]], {key: value for key, value in endpoint.items() if key != "path"}, "medium")
    for store in values["state_model"].get("stores") or []:
        add("state_store_reference", "state_access_pattern", store["references"], {key: value for key, value in store.items() if key != "references"}, "medium")
    for candidate in values["state_model"].get("ownership_candidates") or []:
        add("ambiguous_state_ownership_candidate", "state_access_pattern", candidate["writers"], candidate, "low")
    for crossing in values["trust_model"].get("candidate_crossings") or []:
        add("trust_boundary_crossing_candidate", "trust_pattern", [crossing["path"]], crossing, "low")
    for gap in values["test_architecture"].get("direct_test_gaps") or []:
        add("direct_test_gap", "test_dependency_graph", [gap["path"]], gap, "medium")
    for descriptor in values["deployment_model"].get("descriptors") or []:
        add("deployment_descriptor", "deployment_metadata", [descriptor["path"]], {"kind": descriptor["kind"]})
    for item in values["hotspots"]:
        add("structural_hotspot", "fused_static_metric", [item["path"]], item, "medium")
    for item in values["history"].get("file_churn") or []:
        path = str(item.get("path") or item.get("file") or "")
        add("git_churn", "git_history", [path], item)
    return {
        "schema_version": "mn.architecture.fact_database.v1",
        "fact_count": len(facts),
        "facts": facts,
        "truncated": len(facts) >= max_facts,
        "rule": "Conclusions must cite fact IDs; a fact records observation, not architectural judgment.",
    }


def _deterministic_reconstruction(
    profile: dict[str, Any],
    graph: dict[str, Any],
    state: dict[str, Any],
    trust: dict[str, Any],
    deployment: dict[str, Any],
    history: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": "mn.architecture.reconstruction.v1",
        "components": [item["name"] for item in profile.get("packages") or []],
        "entrypoints": profile.get("entrypoints") or [],
        "internal_dependencies": len(graph.get("edges") or []),
        "external_dependencies": sorted({item.get("import", "").split(".", 1)[0] for item in graph.get("external_imports") or [] if item.get("import")}),
        "state_technologies": [item["technology"] for item in state.get("stores") or []],
        "trust_signals": trust.get("signals") or [],
        "declared_deployment_units": deployment.get("candidate_units") or [],
        "runtime_flows": [],
        "runtime_flow_status": "not_reconstructed_without_supplied_traces",
        "history_status": "available" if history.get("available") else "not_supplied",
        "unknowns": [
            "Runtime dispatch and cross-process flow",
            "Production state authority and consistency guarantees",
            "Observed failure recovery behavior",
            "Effective test coverage and deployment topology",
        ],
    }


def _is_test_path(path: str) -> bool:
    return bool(_TEST_PATH_RE.search(path.replace("\\", "/")))
