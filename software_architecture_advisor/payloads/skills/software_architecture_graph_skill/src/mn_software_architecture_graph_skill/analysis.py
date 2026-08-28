"""Static evidence only; no source execution, writes, subprocesses, or network."""

from __future__ import annotations

import ast
import hashlib
import os
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


DEFAULT_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".java", ".go", ".rs", ".c",
    ".h", ".cpp", ".hpp", ".cs", ".rb", ".php", ".swift", ".kt", ".kts",
}
DEFAULT_EXCLUDED_DIRS = {
    ".git", ".venv", "venv", "node_modules", "vendor", "dist", "build",
    "coverage", ".next", "target",
}
DEFAULT_EXCLUDED_FILES = {".env", ".env.local", "id_rsa", "id_ed25519"}
_IMPORT_PATTERN = re.compile(
    r"(?:^|\n)\s*(?:import\s+(?:[^\n;]*?\s+from\s+)?|export\s+.*?\s+from\s+)[\"']([^\"']+)[\"']",
    re.MULTILINE,
)


def build_inventory(root: str | Path, settings: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return a bounded, non-secret source inventory for a staged directory."""
    base = Path(root).expanduser().resolve()
    if not base.is_dir():
        raise ValueError("The staged source root must be an existing directory.")
    settings = settings or {}
    extensions = {str(item).lower() for item in settings.get("supported_extensions", DEFAULT_EXTENSIONS)}
    excluded_dirs = set(settings.get("excluded_directories", DEFAULT_EXCLUDED_DIRS))
    excluded_files = set(settings.get("excluded_file_names", DEFAULT_EXCLUDED_FILES))
    max_files = int(settings.get("max_files", 12000))
    max_bytes = int(settings.get("max_file_bytes", 1_048_576))
    max_total = int(settings.get("max_total_source_mb", 250)) * 1024 * 1024
    files: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    total_bytes = 0
    truncated = False

    for directory, dir_names, file_names in os.walk(base, topdown=True, followlinks=False):
        dir_names[:] = sorted(name for name in dir_names if name not in excluded_dirs and not name.startswith(".git"))
        for name in sorted(file_names):
            path = Path(directory) / name
            rel = path.relative_to(base).as_posix()
            if name in excluded_files or _looks_sensitive(name):
                skipped.append({"path": rel, "reason": "sensitive_name"})
                continue
            if path.suffix.lower() not in extensions:
                continue
            try:
                size = path.stat().st_size
            except OSError:
                skipped.append({"path": rel, "reason": "unreadable"})
                continue
            if size > max_bytes:
                skipped.append({"path": rel, "reason": "file_too_large"})
                continue
            if len(files) >= max_files or total_bytes + size > max_total:
                truncated = True
                skipped.append({"path": rel, "reason": "inventory_budget_reached"})
                continue
            try:
                data = path.read_bytes()
            except OSError:
                skipped.append({"path": rel, "reason": "unreadable"})
                continue
            if b"\x00" in data[:4096]:
                skipped.append({"path": rel, "reason": "binary_content"})
                continue
            text = data.decode("utf-8", errors="replace")
            lines = text.count("\n") + (1 if text else 0)
            files.append(
                {
                    "path": rel,
                    "module_id": _module_id(rel),
                    "extension": path.suffix.lower(),
                    "bytes": size,
                    "lines": lines,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "package": _package(rel),
                    "text": text,
                }
            )
            total_bytes += size

    language_counts = Counter(_language_for(item["extension"]) for item in files)
    return {
        "schema_version": "mn.architecture.inventory.v1",
        "source_root_name": base.name,
        "source_file_count": len(files),
        "source_bytes": total_bytes,
        "language_counts": dict(sorted(language_counts.items())),
        "truncated": truncated,
        "skipped": skipped,
        "files": files,
        "limitations": [
            "Inventory is static and excludes sensitive names, binaries, unsupported extensions, large files, and ignored directories.",
            "A missing file or dependency signal is not evidence that the behavior or risk is absent.",
        ],
    }


def build_architecture_graph(inventory: dict[str, Any]) -> dict[str, Any]:
    """Build an inspectable internal-import graph from inventory records."""
    files = list(inventory.get("files") or [])
    modules = {item["module_id"]: item for item in files}
    path_to_module = {item["path"]: item["module_id"] for item in files}
    edges: list[dict[str, str]] = []
    external_imports: list[dict[str, str]] = []
    for item in files:
        imports = _imports_for(item)
        for imported in sorted(imports):
            target = _resolve_import(item, imported, modules, path_to_module)
            if target:
                edges.append({"from": item["module_id"], "to": target, "type": "imports", "source_path": item["path"]})
            elif imported and not imported.startswith("."):
                external_imports.append({"from": item["module_id"], "import": imported, "source_path": item["path"]})
    deduped_edges = list({(edge["from"], edge["to"]): edge for edge in edges}.values())
    nodes = [
        {key: item[key] for key in ("module_id", "path", "package", "extension", "lines", "bytes")}
        for item in files
    ]
    return {
        "schema_version": "mn.architecture.graph.v1",
        "nodes": nodes,
        "edges": sorted(deduped_edges, key=lambda item: (item["from"], item["to"])),
        "external_imports": external_imports[:2000],
        "limitations": [
            "Only statically resolvable internal imports create edges.",
            "Dynamic loading, generated source, runtime configuration, reflection, and dependency injection are not resolved.",
        ],
    }


def analyze_graph(graph: dict[str, Any], *, large_module_line_threshold: int = 500) -> dict[str, Any]:
    """Compute deterministic graph metrics and cite paths instead of making narrative claims."""
    nodes = list(graph.get("nodes") or [])
    edges = list(graph.get("edges") or [])
    paths = {node["module_id"]: node.get("path", node["module_id"]) for node in nodes}
    adjacency: dict[str, set[str]] = {node["module_id"]: set() for node in nodes}
    reverse: dict[str, set[str]] = {node["module_id"]: set() for node in nodes}
    cross_boundary: list[dict[str, str]] = []
    for edge in edges:
        source, target = edge["from"], edge["to"]
        if source in adjacency and target in adjacency:
            adjacency[source].add(target)
            reverse[target].add(source)
            if _package_from_module(source) != _package_from_module(target):
                cross_boundary.append({"from": source, "to": target})
    fan_out = sorted(({"module": key, "count": len(value), "path": paths[key]} for key, value in adjacency.items()), key=lambda item: (-item["count"], item["module"]))
    fan_in = sorted(({"module": key, "count": len(value), "path": paths[key]} for key, value in reverse.items()), key=lambda item: (-item["count"], item["module"]))
    cycles = [[{"module": module, "path": paths[module]} for module in cycle] for cycle in _strongly_connected_components(adjacency) if len(cycle) > 1]
    large_modules = sorted(
        ({"module": node["module_id"], "path": node["path"], "lines": node["lines"]} for node in nodes if node.get("lines", 0) >= large_module_line_threshold),
        key=lambda item: (-item["lines"], item["path"]),
    )
    return {
        "schema_version": "mn.architecture.metrics.v1",
        "module_count": len(nodes),
        "dependency_edge_count": len(edges),
        "external_import_count": len(graph.get("external_imports") or []),
        "cycle_count": len(cycles),
        "cycles": cycles,
        "top_fan_out": fan_out[:10],
        "top_fan_in": fan_in[:10],
        "cross_boundary_dependency_count": len(cross_boundary),
        "cross_boundary_dependencies": cross_boundary[:50],
        "large_modules": large_modules[:25],
        "limitations": [
            "Metrics describe static import structure, not runtime call frequency, latency, ownership, security posture, or production reliability.",
            "High fan-in or fan-out is a review signal, not proof that a module is incorrectly designed.",
        ],
    }


def _imports_for(item: dict[str, Any]) -> set[str]:
    if item.get("extension") == ".py":
        try:
            tree = ast.parse(item.get("text") or "")
        except SyntaxError:
            return set()
        imports: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.update(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                prefix = "." * node.level
                imports.add(prefix + module)
                if not module:
                    imports.update(prefix + alias.name for alias in node.names)
        return imports
    return set(match.group(1) for match in _IMPORT_PATTERN.finditer(item.get("text") or ""))


def _resolve_import(item: dict[str, Any], imported: str, modules: dict[str, dict[str, Any]], path_to_module: dict[str, str]) -> str | None:
    if item.get("extension") == ".py":
        current = item["module_id"]
        if imported.startswith("."):
            levels = len(imported) - len(imported.lstrip("."))
            suffix = imported[levels:]
            parent = current.split(".")[:-1]
            if levels > 1:
                parent = parent[: -(levels - 1)]
            candidate = ".".join([*parent, *suffix.split(".")] if suffix else parent)
        else:
            candidate = imported
        for option in (candidate, f"{candidate}.__init__"):
            if option in modules:
                return option
        return None
    if imported.startswith("."):
        base = Path(item["path"]).parent
        candidate = (base / imported).as_posix().replace("./", "")
        for suffix in (".ts", ".tsx", ".js", ".jsx", ".java", ".go", ".rs"):
            matched = path_to_module.get(candidate + suffix) or path_to_module.get(candidate + "/index" + suffix)
            if matched:
                return matched
    return None


def _strongly_connected_components(adjacency: dict[str, set[str]]) -> list[list[str]]:
    index = 0
    stack: list[str] = []
    active: set[str] = set()
    indexes: dict[str, int] = {}
    low_links: dict[str, int] = {}
    result: list[list[str]] = []

    def visit(node: str) -> None:
        nonlocal index
        indexes[node] = index
        low_links[node] = index
        index += 1
        stack.append(node)
        active.add(node)
        for child in sorted(adjacency[node]):
            if child not in indexes:
                visit(child)
                low_links[node] = min(low_links[node], low_links[child])
            elif child in active:
                low_links[node] = min(low_links[node], indexes[child])
        if low_links[node] == indexes[node]:
            component: list[str] = []
            while stack:
                child = stack.pop()
                active.remove(child)
                component.append(child)
                if child == node:
                    break
            result.append(sorted(component))

    for node in sorted(adjacency):
        if node not in indexes:
            visit(node)
    return result


def _module_id(path: str) -> str:
    pure = path.rsplit(".", 1)[0]
    return pure.replace("/", ".")


def _package(path: str) -> str:
    return path.split("/", 1)[0] if "/" in path else "root"


def _package_from_module(module: str) -> str:
    return module.split(".", 1)[0]


def _language_for(extension: str) -> str:
    if extension == ".py":
        return "python"
    if extension in {".js", ".jsx", ".ts", ".tsx"}:
        return "javascript_typescript"
    return extension.removeprefix(".") or "unknown"


def _looks_sensitive(name: str) -> bool:
    lowered = name.lower()
    return any(marker in lowered for marker in ("secret", "credential", "password", "private_key", ".pem", ".p12"))
