"""Typed, source-backed display graph and bounded temporal witnesses from shared skills."""
import hashlib
import json

from .temporal_evidence import paths


def attach(workspace, case, settings):
    sources = {s["source_id"]: s for s in workspace["sources"]}
    evidence = {e["evidence_id"]: e for e in workspace["evidence"]}
    temporal = workspace["temporal"]
    graph = {"nodes": list(temporal["nodes"]), "edges": list(temporal["edges"]),
        "definition": "Directed top-level addressing and explicit source structure; person mappings and legal meaning remain unresolved",
        "coverage": "Header/structural navigation only; complete relationship extraction is not established",
        "display_limit": 49, "path_seed_limit": 16, "path_index": {}}
    index_path = case / "source-relationships.json"
    if index_path.exists():
        index = json.loads(index_path.read_text())
        visible_coverage = [c for c in index['coverage'] if c['source_id'] in sources]
        if any(c.get('unresolved') or c.get('model_status') != 'indexed' for c in visible_coverage):
            graph['coverage'] = 'Partial relationship extraction; missing or unrequested relationships cannot establish absence'
        units = {u["key"]: u for u in index["units"] if u["source_id"] in sources}
        for key, unit in units.items():
            source = sources[unit["source_id"]]
            a, b = unit["start_offset"], unit["end_offset"]
            if (source["content_sha256"] != unit["content_sha256"] or source["text"] is None
                    or not 0 <= a < b <= len(source["text"]) or source["text"][a:b] != unit["text"]):
                raise ValueError("Graph support differs from the authorized frozen source")
            identifier = hashlib.sha256(f'{unit["source_id"]}|{unit["content_sha256"]}|{a}|{b}'.encode()).hexdigest()[:32]
            evidence.setdefault(identifier, {"evidence_id": identifier, "source_id": unit["source_id"],
                "content_sha256": unit["content_sha256"], "start_offset": a, "end_offset": b,
                "text": unit["text"], "provenance_kind": "observed"})
            unit["evidence_id"] = identifier
            graph["nodes"].append({"id": key, "label": unit.get("name") or unit.get("title") or source["relative_path"],
                "kind": "source_unit", "source_id": unit["source_id"], "evidence_id": identifier,
                "identity_status": "Frozen source unit; generated locator"})
        for index_number, relation in enumerate(index["relations"]):
            if relation["source"] not in units or relation["target"] not in units or not set(relation["support"]) <= set(units):
                continue
            graph["edges"].append({"id": "L-" + str(index_number), **relation,
                "evidence_refs": [evidence[units[k]["evidence_id"]] for k in relation["support"]],
                "display_time": "No event date established", "kind": relation.get("kind", "source_structure")})
    for node in temporal["nodes"][:graph["path_seed_limit"]]:
        result = paths(temporal, [node["id"]], workspace["access_scope"])
        # Source references already live in the shared evidence set. Retain order,
        # uncertainty checks and frontier instead of duplicating excerpts per path.
        graph["path_index"][node["id"]] = {key: result[key] for key in ("status", "unresolved", "frontier", "qualification")}
        for key in ("paths", "partial_paths", "rejected_paths"):
            graph["path_index"][node["id"]][key] = [{"seed": p["seed"], "target": p["target"],
                "edge_ids": [e["id"] for e in p["edges"]], "temporal_checks": p.get("temporal_checks", [])} for p in result[key]]
    workspace["graph"] = graph
    workspace["evidence"] = list(evidence.values())
    return workspace
