"""Capture immutable inputs; do not construct derived layers or call models."""
import fnmatch
import fcntl
import json
import os
from pathlib import Path
import subprocess
import time
from uuid import uuid4

from mn_graph_analysis_skill import (GraphClient, FileIdentityRegistry, file_logical_id,
    get_repository_identity, git_rename_hints)
from mn_beam_analysis_skill import analyze_sources
from .ingest import digest, logical_id, module_name, EXTENSIONS


def capture(repository, workspace, config, facts_path=None, input_info=None):
    repository, workspace = Path(repository).resolve(strict=True), Path(workspace).resolve()
    if not repository.is_dir() or repository == workspace:
        raise ValueError("Repository must be a directory distinct from the output workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    # Identity reconciliation and CURRENT publication must share one baseline.
    with (workspace / "capture.lock").open("a") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        return _capture(repository, workspace, config, facts_path, input_info)


def _capture(repository, workspace, config, facts_path=None, input_info=None):
    began = time.perf_counter()
    repository = Path(repository).resolve(strict=True)
    workspace = Path(workspace).resolve()
    if not repository.is_dir() or repository == workspace:
        raise ValueError("Repository must be a directory distinct from the output workspace")
    workspace.mkdir(parents=True, exist_ok=True)
    cfg = config["ingest"]
    excluded = {name.casefold() for name in cfg["exclude"]}
    sources, modules, warnings, skipped = {}, {}, [], {}
    total = 0
    for base, dirs, files in os.walk(repository, followlinks=False):
        skipped["excluded_directories"] = skipped.get("excluded_directories", 0) + sum(d.casefold() in excluded for d in dirs)
        dirs[:] = sorted(d for d in dirs if d.casefold() not in excluded and (not d.startswith(".") or d == ".github")
                         and not (Path(base) / d).is_symlink() and not (workspace.is_relative_to(repository) and (Path(base) / d).resolve().is_relative_to(workspace)))
        for filename in sorted(files):
            path = Path(base) / filename
            if path.is_symlink():
                continue
            if path.suffix not in EXTENSIONS and filename != "Dockerfile":
                skipped["non_code_files"] = skipped.get("non_code_files", 0) + 1
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
        raise ValueError("No supported code sources found")
    beam = analyze_sources({path: source["text"] for path, source in sources.items()},
                               max_files=cfg["max_files"], max_file_bytes=cfg["max_file_bytes"],
                               max_total_bytes=cfg["max_total_bytes"])
    for item in beam["modules"]:
        name, rel = item["name"], item["path"]
        if name in modules:
            raise ValueError(f"Ambiguous module {name}")
        layer = next((key for key, patterns in cfg["layers"].items() if any(fnmatch.fnmatch(rel, p) for p in patterns)), "unspecified")
        modules[name] = {**item, "layer": layer, "layer_basis": "configured path pattern"}
    warnings.extend(f"{item['path']}:{item['line']}: {item['reason']}" for item in beam["warnings"])
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
    previous, prior_manifest = None, {}
    if (workspace / "CURRENT").exists():
        prior_id = (workspace / "CURRENT").read_text().strip()
        if not prior_id.isalnum():
            raise ValueError("Invalid snapshot pointer")
        prior = workspace / "snapshots" / prior_id
        prior_manifest = json.loads((prior / "manifest.json").read_text())
        if (prior / "file-identities.json").exists():
            previous = json.loads((prior / "file-identities.json").read_text())
    repository_id = get_repository_identity(repository,
        repository_id=cfg.get("repository_id") or (input_info or {}).get("repository_id"),
        previous_id=previous["repository_id"] if previous else None)
    if previous and previous["repository_id"] != repository_id:
        previous, prior_manifest = None, {}
    registry = FileIdentityRegistry(repository_id, previous)
    identities = registry.reconcile({p: s["sha256"] for p, s in sources.items()},
        renames=git_rename_hints(repository, prior_manifest.get("git_anchor")))
    identifier = uuid4().hex
    directory = workspace / "snapshots" / identifier
    directory.mkdir(parents=True)
    nodes = [{"id": logical_id("module:" + name), "kind": "Module", "labels": ["Module"],
              "properties": {"key": "module:" + name, **module, "file_node_id": identities[module["path"]]["node_id"],
                             "sha256": sources[module["path"]]["sha256"]}} for name, module in modules.items()]
    for path, identity in identities.items():
        nodes.append({"id": file_logical_id(identity["node_id"]), "kind": "File", "labels": ["File"],
            "properties": {**identity, "key": "file:" + identity["node_id"], "path": path,
                           "language": Path(path).suffix.lstrip(".") or "dockerfile"}})
    if len({n["id"] for n in nodes}) != len(nodes):
        raise ValueError("File/module logical-ID collision")
    # Existing parser-owned module/symbol IDs remain compatible. This explicit
    # link anchors them to the independently persistent file entity.
    edges = [{"id": logical_id("declared-in:" + name + ":" + identities[module["path"]]["node_id"]),
        "src": logical_id("module:" + name), "dst": file_logical_id(identities[module["path"]]["node_id"]),
        "rel_type": "DECLARED_IN", "properties": {"evidence_ids": []}} for name, module in modules.items()]
    for filename, value in (("nodes.json", nodes), ("edges.json", edges), ("sources.json", sources),
                            ("file-identities.json", registry.export()), ("evidence.json", {}), ("graph-inputs.json", supplied)):
        (directory / filename).write_text(json.dumps(value))
    client = GraphClient(directory / "graph.rgx", config["graph"]["binary"], config["graph"]["timeout_seconds"])
    client.import_json(directory / "nodes.json", directory / "edges.json")
    client.check()
    manifest = {"id": identifier, "format_version": 2, "repository": str(repository), "git_anchor": anchor,
                "input": {**(input_info or {"kind": "folder", "location": str(repository)}), "revision": anchor},
                "extractor": "source-capture/4", "repository_id": repository_id,
                "file_identity_version": registry.export()["version"],
                "sources": {p: s["sha256"] for p, s in sources.items()}, "modules": modules,
                "embedding_config": config["embedding"], "embedding_dimension": None, "ingest_config": cfg,
                "coverage": {"source_files": len(sources), "source_scope": "code_only", "parsed_python_modules": None,
                             "parsed_beam_files": beam["parsed_files"], "beam_limitations": beam["limitations"], "skipped": skipped,
                             "internal_dependency_pairs": None, "history": {"status": "not_materialized", "anchor": anchor},
                             "runtime_traces": "not_collected", "incidents": "not_materialized", "workflows": "not_materialized",
                             "semantic_retrieval": "not_materialized"}, "warnings": warnings,
                "metrics": {"nodes": len(nodes), "edges": len(edges), "embedding_requests": 0, "embedding_cache_hits": 0,
                            "ingestion_ms": round((time.perf_counter() - began) * 1000, 2)}}
    (directory / "manifest.json").write_text(json.dumps(manifest, indent=2))
    pointer = workspace / ("current-" + identifier + ".tmp")
    pointer.write_text(identifier)
    pointer.replace(workspace / "CURRENT")
    return manifest
