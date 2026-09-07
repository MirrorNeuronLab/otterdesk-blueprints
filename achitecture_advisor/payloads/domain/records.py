"""Provenance-preserving graph records and explicit external-evidence contract."""
import json
import re
from .catalog import EXPORT_RELATIONS, LAYERS
from .ingest import digest, logical_id


def validate_export(bundle, sources, modules):
    known = {"module:" + m for m in modules}
    if bundle["version"] == 1:
        kinds = {"DEPENDS_ON", "ACCESSES", "PARTICIPATES_IN", "AFFECTED_BY"}
        for edge in bundle.get("relationships", []):
            if edge["type"] not in kinds or edge["from"] not in modules:
                raise ValueError("Invalid legacy export relation")
            if edge["type"] == "DEPENDS_ON" and edge["to"] not in modules:
                raise ValueError("Unknown export module")
            check_span(sources, edge["source"], edge["line"], edge.get("end_line", edge["line"]))
        return
    for layer, records in bundle.get("layers", {}).items():
        if layer not in EXPORT_RELATIONS:
            raise ValueError(f"Unknown export graph layer: {layer}")
        for node in records.get("nodes", []):
            if not isinstance(node.get("key"), str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*", node.get("kind", "")):
                raise ValueError("Export nodes require string key and a valid kind")
            if node["key"] in known:
                raise ValueError(f"Duplicate export node key: {node['key']}")
            known.add(node["key"])
    for layer, records in bundle.get("layers", {}).items():
        for edge in records.get("edges", []):
            if edge["type"] not in EXPORT_RELATIONS[layer] or edge["source"] not in known or edge["target"] not in known:
                raise ValueError(f"Unsupported {layer} relation or unknown endpoint")
            check_span(sources, edge["source_path"], edge["line"], edge.get("end_line", edge["line"]))


def check_span(sources, path, first, last):
    if path not in sources or type(first) is not int or type(last) is not int or not 1 <= first <= last <= len(sources[path]["text"].splitlines()):
        raise ValueError(f"Invalid evidence span: {path}:{first}-{last}")


class Records:
    def __init__(self, sources, layer, scope, known=None):
        self.sources, self.layer, self.scope = sources, layer, scope
        self.nodes, self.edges, self.evidence = {}, {}, {}
        self.known = dict(known or {})
        self.details = {"limitations": [], "warnings": []}

    def node(self, key, node_kind, **properties):
        identifier = logical_id(key)
        prior = self.known.get(identifier)
        if prior and (prior["properties"]["key"] != key or prior["kind"] != node_kind):
            raise ValueError("Node identity collision")
        record = {"id": identifier, "kind": node_kind, "labels": [node_kind], "properties": {**(prior["properties"] if prior else {}), "key": key, **properties}}
        self.nodes[identifier] = record
        self.known[identifier] = record
        return key

    def cite(self, path, line, end=None, kind="extracted", detail=""):
        end = line if end is None else end
        check_span(self.sources, path, line, end)
        source = self.sources[path]
        value = {"path": path, "sha256": source["sha256"], "line_start": line, "line_end": end,
                 "kind": kind, "text": "".join(source["text"].splitlines(keepends=True)[line-1:end]),
                 "detail": detail, "extractor": "architecture-layers/2"}
        identifier = "E" + digest(json.dumps(value, sort_keys=True).encode())[:20]
        self.evidence[identifier] = {"id": identifier, **value}
        return identifier

    def edge(self, source, target, relation, eid, kind="extracted", detail=""):
        key = f"{logical_id(source)}|{relation}|{logical_id(target)}"
        identifier = logical_id(key)
        if identifier not in self.edges:
            self.edges[identifier] = {"id": identifier, "src": logical_id(source), "dst": logical_id(target),
                                      "rel_type": relation, "properties": {"evidence_ids": [], "kind": kind, "detail": detail}}
        if eid not in self.edges[identifier]["properties"]["evidence_ids"]:
            self.edges[identifier]["properties"]["evidence_ids"].append(eid)

    def finish(self):
        # Node-backed relation views expose evidence and metadata despite RGX's
        # prototype limitation on projecting relationship properties.
        for edge in list(self.edges.values()):
            src, dst = self.known.get(edge["src"]), self.known.get(edge["dst"])
            if src is None or dst is None:
                raise ValueError("Graph relation references an unmaterialized endpoint")
            a, b = src["properties"], dst["properties"]
            self.node(f"relation:{self.layer}:{self.scope}:{edge['id']}", "EvidenceRelation",
                      layer=self.layer, source_name=a.get("qualified_name", a.get("name", a["key"])),
                      target_name=b.get("qualified_name", b.get("name", b["key"])),
                      module=a.get("module", a.get("name", "") if src["kind"] == "Module" else ""),
                      target_module=b.get("module", b.get("name", "") if dst["kind"] == "Module" else ""),
                      source_key=a["key"], target_key=b["key"], relation=edge["rel_type"], **edge["properties"])
        return {"nodes": list(self.nodes.values()), "edges": list(self.edges.values()),
                "evidence": self.evidence, "details": self.details}


def add_export(records, bundle, modules):
    layer = records.layer
    if bundle["version"] == 1:
        mapping = {"DEPENDS_ON": ("dependencies", "Module"), "ACCESSES": ("state", "Table"),
                   "PARTICIPATES_IN": ("workflow", "Workflow"), "AFFECTED_BY": ("incidents", "Incident")}
        count = 0
        for item in bundle.get("relationships", []):
            family, kind = mapping[item["type"]]
            if family != layer:
                continue
            target = kind.lower() + ":" + item["to"]
            if kind != "Module":
                records.node(target, kind, name=item["to"])
            eid = records.cite(item["source"], item["line"], item.get("end_line"), "supplied", "Explicit export; not independently verified")
            records.edge("module:" + item["from"], target, item["type"], eid, "supplied")
            count += 1
        return count
    content = bundle.get("layers", {}).get(layer)
    if content is None:
        return None
    # Include declared endpoints from all export families, but no unrelated edges.
    for family in bundle.get("layers", {}).values():
        for node in family.get("nodes", []):
            records.node(node["key"], node["kind"], **node.get("properties", {}))
    count = 0
    for edge in content.get("edges", []):
        if LAYERS[layer].scoped:
            owners = {records.known[logical_id(edge[endpoint])]["properties"].get("module", "") for endpoint in ("source", "target")}
            owners.update(edge[endpoint][7:] for endpoint in ("source", "target") if edge[endpoint].startswith("module:"))
            if not owners.intersection(modules):
                raise ValueError(f"Scoped {layer} export endpoints require an indexed module property")
            if records.scope not in owners:
                continue
        count += 1
        eid = records.cite(edge["source_path"], edge["line"], edge.get("end_line"), "supplied", "Explicit export; not independently verified")
        records.edge(edge["source"], edge["target"], edge["type"], eid, "supplied", json.dumps(edge.get("properties", {}), sort_keys=True))
    return count
