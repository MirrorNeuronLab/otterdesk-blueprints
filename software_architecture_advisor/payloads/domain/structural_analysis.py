"""Deterministic, source-linked dependency baseline for a frozen snapshot."""

import csv
import json
from pathlib import Path

from mn_sdk.step_runtime import artifact_reference

from .config import validate_config, offline_config
from .lazy import LayerManager


def _components(adjacency):
    """Iterative Kosaraju traversal keeps large source inventories bounded by graph size."""
    reverse = {name: set() for name in adjacency}
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].add(source)
    seen, order = set(), []
    for root in sorted(adjacency):
        if root in seen:
            continue
        seen.add(root)
        stack = [(root, iter(sorted(adjacency[root])))]
        while stack:
            node, children = stack[-1]
            child = next(children, None)
            if child is None:
                order.append(node)
                stack.pop()
            elif child not in seen:
                seen.add(child)
                stack.append((child, iter(sorted(adjacency[child]))))
    seen.clear()
    components = []
    for root in reversed(order):
        if root in seen:
            continue
        component, pending = [], [root]
        seen.add(root)
        while pending:
            node = pending.pop()
            component.append(node)
            for parent in sorted(reverse[node]):
                if parent not in seen:
                    seen.add(parent)
                    pending.append(parent)
        components.append(sorted(component))
    return sorted(components, key=lambda group: (group[0], len(group)))


def _bridge_modules(adjacency):
    """Articulation vertices of the undirected projection, without recursion."""
    neighbors = {name: set(targets) for name, targets in adjacency.items()}
    for source, targets in adjacency.items():
        for target in targets:
            neighbors[target].add(source)
    discovered, low, parent, children, bridges = {}, {}, {}, {}, set()
    for root in sorted(neighbors):
        if root in discovered:
            continue
        parent[root] = None
        children[root] = 0
        discovered[root] = low[root] = len(discovered)
        stack = [(root, iter(sorted(neighbors[root])))]
        while stack:
            node, adjacent = stack[-1]
            neighbor = next(adjacent, None)
            if neighbor is None:
                stack.pop()
                ancestor = parent[node]
                if ancestor is None:
                    if children[node] > 1:
                        bridges.add(node)
                else:
                    low[ancestor] = min(low[ancestor], low[node])
                    if parent[ancestor] is not None and low[node] >= discovered[ancestor]:
                        bridges.add(ancestor)
            elif neighbor not in discovered:
                parent[neighbor] = node
                children[node] += 1
                children[neighbor] = 0
                discovered[neighbor] = low[neighbor] = len(discovered)
                stack.append((neighbor, iter(sorted(neighbors[neighbor]))))
            elif neighbor != parent[node]:
                low[node] = min(low[node], discovered[neighbor])
    return sorted(bridges)


def analyze_dependencies(snapshot, nodes, edges, evidence, *, max_dsm_modules):
    modules = snapshot["modules"]
    names = sorted(modules)
    by_id = {node["id"]: node for node in nodes}
    adjacency = {name: set() for name in names}
    relations = {}
    for edge in edges:
        if edge["rel_type"] != "DEPENDS_ON":
            continue
        source = by_id[edge["src"]]["properties"]["key"]
        target = by_id[edge["dst"]]["properties"]["key"]
        if not source.startswith("module:") or not target.startswith("module:"):
            continue
        source, target = source[7:], target[7:]
        if source not in adjacency or target not in adjacency:
            raise ValueError("Dependency relation references an unindexed module")
        ids = edge["properties"]["evidence_ids"]
        if not ids or any(identifier not in evidence for identifier in ids):
            raise ValueError("Dependency relation lacks exact source evidence")
        adjacency[source].add(target)
        relations[(source, target)] = sorted(set(relations.get((source, target), [])) | set(ids))
    reverse = {name: set() for name in names}
    for source, targets in adjacency.items():
        for target in targets:
            reverse[target].add(source)
    cycles = [group for group in _components(adjacency) if len(group) > 1 or group[0] in adjacency[group[0]]]
    ranking = sorted(names, key=lambda name: (-len(reverse[name]) - len(adjacency[name]), -len(reverse[name]), name))
    result = {
        "schema_version": "mn.architecture.structural_analysis.v1",
        "snapshot": snapshot["id"],
        "method": "Frozen module DEPENDS_ON edges only; direction is importing module to imported module.",
        "coverage": {"indexed_modules": len(names), "dependency_edges": len(relations),
                     "source_files": snapshot["coverage"]["source_files"],
                     "python_module_candidates": sum(info["path"].endswith(".py") for info in modules.values()),
                     "skipped": snapshot["coverage"].get("skipped", {}),
                     "unsupported_runtime_relationships": "not measured"},
        "modules": names,
        "dependencies": [{"source": source, "target": target, "evidence_ids": ids,
                          "source_locations": [{key: evidence[eid][key] for key in ("path", "sha256", "line_start", "line_end")}
                                               for eid in ids]}
                         for (source, target), ids in sorted(relations.items())],
        "fan_in": {name: len(reverse[name]) for name in names},
        "fan_out": {name: len(adjacency[name]) for name in names},
        "degree_centrality": {name: round((len(reverse[name]) + len(adjacency[name])) / max(1, 2 * (len(names) - 1)), 6)
                              for name in names},
        "top_coupled_modules": ranking[:10],
        "strongly_connected_cycles": cycles,
        "bridge_modules": _bridge_modules(adjacency),
        "dsm": {"status": "ready" if len(names) <= max_dsm_modules else "omitted_size_limit",
                "path": "analysis/dependency-dsm.csv" if len(names) <= max_dsm_modules else None,
                "max_modules": max_dsm_modules,
                "orientation": "row imports column; 1 means a direct source or supplied dependency"},
        "limits": ["A dependency cycle is a static relationship, not a demonstrated runtime failure.",
                   "A bridge module connects the undirected source graph; it is not necessarily a runtime chokepoint.",
                   "Degree measures local graph connectivity, not severity, business value, or change impact.",
                   "Unresolved imports and unsupported languages may hide dependencies."],
    }
    return result, adjacency


def _write_dsm(path, names, adjacency):
    with path.open("w", encoding="utf-8", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["module", *names])
        for source in names:
            writer.writerow([source, *(1 if target in adjacency[source] else 0 for target in names)])


def analyze_snapshot(context, *, llm_client=None):
    root = Path(context["run_dir"])
    snapshot = json.loads((root / "snapshot.json").read_text(encoding="utf-8"))
    cfg = validate_config(context["config"])
    if cfg["offline"]:
        cfg = offline_config(cfg)
    directory = root / "evidence" / "snapshots" / snapshot["id"]
    manager = LayerManager(directory, cfg)
    generation = manager.ensure(("dependencies",))
    active = Path(generation["directory"])
    result, adjacency = analyze_dependencies(
        snapshot,
        json.loads((active / "nodes.json").read_text()),
        json.loads((active / "edges.json").read_text()),
        json.loads((active / "evidence.json").read_text()),
        max_dsm_modules=cfg["analysis"]["max_dsm_modules"],
    )
    details = generation["entries"]["dependencies:*"]["details"]
    result["coverage"]["unresolved_imports"] = len(details.get("unresolved_imports", []))
    result["coverage"]["parse_warnings"] = details.get("warnings", [])[:20]
    result["coverage"]["omitted_parse_warnings"] = max(0, len(details.get("warnings", [])) - 20)
    output = root / "analysis"
    output.mkdir(parents=True, exist_ok=True)
    result_path = output / "dependencies.json"
    result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    refs = [artifact_reference("structural_analysis", "analysis/dependencies.json")]
    if result["dsm"]["status"] == "ready":
        _write_dsm(output / "dependency-dsm.csv", result["modules"], adjacency)
        refs.append(artifact_reference("dependency_dsm", "analysis/dependency-dsm.csv"))
    return {"analysis": refs[0], "modules": len(result["modules"]),
            "dependencies": len(result["dependencies"]), "cycles": len(result["strongly_connected_cycles"]),
            "dsm_status": result["dsm"]["status"]}, refs
