"""Capture immutable inputs; do not construct derived layers or call models."""
import fnmatch
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from mn_graph_analysis_skill import GraphClient
from .ingest import digest, logical_id, module_name, EXTENSIONS


EXTRA = {".json", ".yaml", ".yml", ".toml", ".ini"}


def capture(repository, workspace, config, facts_path=None, input_info=None):
    began = time.perf_counter()
    repository = Path(repository).resolve(strict=True)
    workspace = Path(workspace).resolve()
    if not repository.is_dir() or repository == workspace:
        raise ValueError("Repository must be a directory distinct from the output workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    cfg = config["ingest"]
    sources, modules, warnings, skipped = {}, {}, [], {}
    total = 0
    for base, dirs, files in os.walk(repository, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in cfg["exclude"] and (not d.startswith(".") or d == ".github")
                         and not (Path(base) / d).is_symlink() and not (workspace.is_relative_to(repository) and (Path(base) / d).resolve().is_relative_to(workspace)))
        for filename in sorted(files):
            path = Path(base) / filename
            if path.is_symlink() or (path.suffix not in EXTENSIONS | EXTRA and filename not in {"CODEOWNERS", "Dockerfile"}):
                continue
            if path.stat().st_size > cfg["max_file_bytes"]:
                skipped["oversized_files"] = skipped.get("oversized_files", 0) + 1
                continue
            if len(sources) >= cfg["max_files"]:
                raise ValueError("File limit exceeded")
            content = path.read_bytes()
            total += len(content)
            if total > cfg["max_total_bytes"]:
                raise ValueError("Repository byte limit exceeded")
            try:
                text = content.decode("utf-8")
            except UnicodeDecodeError:
                skipped["non_utf8"] = skipped.get("non_utf8", 0) + 1
                continue
            rel = path.relative_to(repository).as_posix()
            sources[rel] = {"sha256": digest(content), "text": text}
            if path.suffix == ".py":
                name = module_name(rel, cfg["source_roots"])
                if name in modules:
                    raise ValueError(f"Ambiguous module {name}; configure source roots")
                layer = next((key for key, patterns in cfg["layers"].items() if any(fnmatch.fnmatch(rel, p) for p in patterns)), "unspecified")
                modules[name] = {"name": name, "path": rel, "layer": layer, "layer_basis": "configured path pattern"}
    if not sources:
        raise ValueError("No supported text sources found")
    supplied = {"version": 2, "modules": [], "layers": {}}
    if facts_path:
        supplied = json.loads(Path(facts_path).read_bytes())
        if supplied.get("version") not in {1, 2}:
            raise ValueError("Graph export version must be 1 or 2")
        for item in supplied.get("modules", []):
            if item["path"] not in sources:
                raise ValueError("Export module must refer to an indexed source")
            if item["name"] in modules and modules[item["name"]]["path"] != item["path"]:
                raise ValueError("Export module conflicts with extracted module")
            modules[item["name"]] = {**item, "layer": item.get("layer", "unspecified"), "layer_basis": "supplied declaration"}
        from .records import validate_export
        validate_export(supplied, sources, modules)
    anchor = None
    if (repository / ".git").exists():
        try:
            anchor = subprocess.run(["git", "-C", str(repository), "-c", f"safe.directory={repository}", "rev-parse", "HEAD"],
                                    capture_output=True, text=True, check=True, timeout=10).stdout.strip()
        except (OSError, subprocess.SubprocessError):
            warnings.append("Git HEAD could not be captured; history queries will report unavailable")
    identifier = uuid4().hex
    directory = workspace / "snapshots" / identifier
    directory.mkdir(parents=True)
    nodes = [{"id": logical_id("module:" + name), "kind": "Module", "labels": ["Module"],
              "properties": {"key": "module:" + name, **module, "sha256": sources[module["path"]]["sha256"]}} for name, module in modules.items()]
    for filename, value in (("nodes.json", nodes), ("edges.json", []), ("sources.json", sources), ("evidence.json", {}), ("graph-inputs.json", supplied)):
        (directory / filename).write_text(json.dumps(value))
    client = GraphClient(directory / "graph.rgx", config["graph"]["binary"], config["graph"]["timeout_seconds"])
    client.import_json(directory / "nodes.json", directory / "edges.json")
    client.check()
    manifest = {"id": identifier, "format_version": 2, "repository": str(repository), "git_anchor": anchor,
                "input": {**(input_info or {"kind": "folder", "location": str(repository)}), "revision": anchor},
                "extractor": "source-capture/2", "sources": {p: s["sha256"] for p, s in sources.items()}, "modules": modules,
                "embedding_config": config["embedding"], "embedding_dimension": None, "ingest_config": cfg,
                "coverage": {"source_files": len(sources), "parsed_python_modules": None, "skipped": skipped,
                             "internal_dependency_pairs": None, "history": {"status": "not_materialized", "anchor": anchor},
                             "runtime_traces": "not_collected", "incidents": "not_materialized", "workflows": "not_materialized",
                             "semantic_retrieval": "not_materialized"}, "warnings": warnings,
                "metrics": {"nodes": len(nodes), "edges": 0, "embedding_requests": 0, "embedding_cache_hits": 0,
                            "ingestion_ms": round((time.perf_counter() - began) * 1000, 2)}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    pointer = workspace / ("current-" + identifier + ".tmp")
    pointer.write_text(identifier)
    pointer.replace(workspace / "CURRENT")
    return manifest
