"""Allowlisted, parameterized graph tools with durable query receipts."""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import time

from mn_graph_analysis_skill import GraphClient, ensure_readonly_rgql
from .ingest import make_embedder, logical_id
from .lazy import LayerManager
from .catalog import LayerUnavailable
from .events import emit
from .query_catalog import REQUIREMENTS, VIEWS, LAYER_QUERIES


QUERIES = {
    "symbols": "MATCH (a:Module)-[:DECLARES]->(s:Symbol) WHERE a.name = $module RETURN s.name AS symbol, s.line AS line, s.end_line AS end_line, s.path AS path LIMIT {limit}",
    "hotspots": "MATCH (a:Module)-[:DEPENDS_ON]->(b:Module) RETURN b.name AS module, count(*) AS inbound ORDER BY inbound DESC LIMIT {limit}",
    "inbound_count": "MATCH (a:Module)-[:DEPENDS_ON]->(b:Module) WHERE b.name = $module RETURN count(*) AS inbound_dependency_pairs",
    "dependencies": "MATCH (a:Module)-[e:DEPENDS_ON]->(b:Module) WHERE a.name = $module OR b.name = $module RETURN a.name AS source, b.name AS target, a.key AS source_key, b.key AS target_key LIMIT {limit}",
    "tables": "MATCH (a:Module)-[e:ACCESSES]->(t:Table) WHERE a.name = $module RETURN t.name AS table_name, a.key AS source_key, t.key AS target_key LIMIT {limit}",
    "shared_tables": "MATCH (a:Module)-[e:ACCESSES]->(t:Table)<-[f:ACCESSES]-(b:Module) WHERE a.name = $module AND b.name <> $module RETURN b.name AS other_module, t.name AS table_name, a.key AS source_key, t.key AS target_key, b.key AS other_source_key, t.key AS other_target_key LIMIT {limit}",
    "cycles": "MATCH (a:Module)-[e:DEPENDS_ON]->(b:Module)-[f:DEPENDS_ON]->(c:Module) WHERE a.name = $module AND c.name = $module RETURN b.name AS peer, a.key AS source_key, b.key AS target_key, b.key AS other_source_key, c.key AS other_target_key LIMIT {limit}",
    "blast_radius": "MATCH (a:Module)-[:DEPENDS_ON*1..3]->(b:Module) WHERE b.name = $module RETURN DISTINCT a.name AS dependent_module LIMIT {limit}",
    "layers": "MATCH (a:Module)-[e:DEPENDS_ON]->(b:Module) WHERE a.name = $module RETURN a.layer AS source_layer, b.name AS target, b.layer AS target_layer, a.key AS source_key, b.key AS target_key LIMIT {limit}",
    "cochange": "MATCH (a:Module)<-[:CHANGES]-(c:Commit)-[:CHANGES]->(b:Module) WHERE a.name = $module AND b.name <> $module RETURN b.name AS other_module, count(*) AS shared_commits ORDER BY shared_commits DESC LIMIT {limit}",
    "changes": "MATCH (c:Commit)-[:CHANGES]->(a:Module) WHERE a.name = $module RETURN count(*) AS commits_in_window",
    "workflows": "MATCH (a:Module)-[e:PARTICIPATES_IN]->(w:Workflow) WHERE a.name = $module RETURN w.name AS workflow, a.key AS source_key, w.key AS target_key LIMIT {limit}",
    "incidents": "MATCH (a:Module)-[e:AFFECTED_BY]->(i:Incident) WHERE a.name = $module RETURN i.name AS incident, a.key AS source_key, i.key AS target_key LIMIT {limit}",
}

QUERIES.update(LAYER_QUERIES)


def normalize(value):
    if value == "Null":
        return None
    if isinstance(value, list):
        return [normalize(v) for v in value]
    if isinstance(value, dict):
        if len(value) == 1 and next(iter(value)) in {"String", "Int64", "UInt64", "Float64", "Boolean", "Bool", "List", "Vector", "Null"}:
            return normalize(next(iter(value.values())))
        return {k: normalize(v) for k, v in value.items()}
    return value


class QuerySession:
    def __init__(self, workspace: Path, config: dict, snapshot_id: str | None = None, progress=None):
        self.config = config
        self.progress = progress
        snapshot_id = snapshot_id or (workspace / "CURRENT").read_text().strip()
        if not snapshot_id.isalnum():
            raise ValueError("Invalid snapshot ID")
        self.directory = workspace / "snapshots" / snapshot_id
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        self.layers = LayerManager(self.directory, config, progress=progress) if self.manifest.get("format_version") == 2 else None
        self.receipts, self.materializations = [], []
        self.cache = {}
        self.embedder = None
        self._activate(self.layers.current() if self.layers else {"id": "legacy", "entries": {}, "directory": str(self.directory)})

    def _activate(self, generation):
        if generation["id"] == getattr(self, "generation", None):
            return
        active = Path(generation["directory"])
        self.generation = generation["id"]
        self.active_directory = active
        self.evidence = {**getattr(self, "evidence", {}), **json.loads((active / "evidence.json").read_text())}
        edge_bytes = (active / "edges.json").read_bytes()
        self.edge_manifest_sha256 = hashlib.sha256(edge_bytes).hexdigest()
        self.edge_evidence = {(e["src"], e["dst"], e["rel_type"]): e["properties"]["evidence_ids"] for e in json.loads(edge_bytes)}
        self.client = GraphClient(active / "graph.rgx", self.config["graph"]["binary"], self.config["graph"]["timeout_seconds"])
        emit("graph.generation.activated", generation=self.generation, edge_manifest_sha256=self.edge_manifest_sha256)
        if self.layers:
            status = self.layers.status()
            self.manifest["coverage"]["graph_layers"] = {k: v["status"] for k, v in status["layers"].items()}
            for entry in generation["entries"].values():
                layer, details = entry["layer"], entry["details"]
                if layer == "dependencies":
                    self.manifest["coverage"]["internal_dependency_pairs"] = sum(k[2] == "DEPENDS_ON" for k in self.edge_evidence)
                if layer == "symbols":
                    self.manifest["coverage"]["parsed_python_modules"] = details.get("parsed_python_modules")
                if layer == "git":
                    self.manifest["coverage"]["history"] = details.get("history", {"status": "supplied"})
                if layer in {"workflow", "incidents"}:
                    self.manifest["coverage"]["workflows" if layer == "workflow" else "incidents"] = "supplied"
                if layer == "embeddings":
                    self.manifest["embedding_dimension"] = details["embedding_dimension"]
                    self.manifest["coverage"]["semantic_retrieval"] = details["semantic_retrieval"]

    def _prepare(self, tool, module=""):
        if len(self.receipts) >= self.config["investigation"]["max_queries"]:
            raise ValueError("Investigation query budget exhausted")
        if self.layers is None:
            if tool in LAYER_QUERIES:
                raise ValueError("Re-ingest this legacy snapshot to enable multi-graph queries")
            return
        began = time.perf_counter()
        emit("graph.requirements.requested", tool=tool, layers=list(REQUIREMENTS[tool]), module=module)
        try:
            generation = self.layers.ensure(REQUIREMENTS[tool], module)
            self.materializations.extend(self.layers.events)
            self._activate(generation)
        except Exception as exc:
            self.materializations.extend(self.layers.events)
            self.manifest["coverage"]["graph_layers"] = {k: v["status"] for k, v in self.layers.status()["layers"].items()}
            self.receipts.append({"id": f"Q{len(self.receipts)+1:04d}", "tool": tool,
                "query": QUERIES.get(tool, "semantic cosine search"), "params": {"module": module},
                "snapshot": self.manifest["id"], "generation": self.generation, "exhaustive": False,
                "rows": [], "status": "unavailable" if isinstance(exc, LayerUnavailable) else "error",
                "error": f"{type(exc).__name__}: {exc}", "elapsed_ms": round((time.perf_counter()-began)*1000, 3)})
            raise

    def _execute(self, tool, query, params, exhaustive=False):
        ensure_readonly_rgql(query)
        key = json.dumps([self.generation, query, params], sort_keys=True)
        if key in self.cache:
            cached = self.cache[key]
            emit("query.cache_hit", query_id=cached["id"], tool=tool, query=query, params=params,
                 generation=self.generation, row_count=len(cached["rows"]), result_sha256=cached.get("result_sha256"))
            return cached
        if len(self.receipts) >= self.config["investigation"]["max_queries"]:
            raise ValueError("Investigation query budget exhausted")
        began = time.perf_counter()
        record = {"id": f"Q{len(self.receipts) + 1:04d}", "tool": tool, "query": query,
                  "params": params, "snapshot": self.manifest["id"], "generation": self.generation, "exhaustive": exhaustive}
        self.receipts.append(record)
        emit("query.started", query_id=record["id"], tool=tool, query=query, params=params,
             generation=self.generation, exhaustive=exhaustive)
        try:
            raw = self.client.query(query, params)
            record["raw_result"] = raw
            record["rows"] = [normalize(row.get("fields", row)) for row in raw.get("rows", [])]
            # RGX's current MATCH edge values lack stable logical IDs/properties.
            # Join returned endpoint keys + the fixed relation type to the source
            # projection. Keep raw rows and this derivation explicit in the receipt.
            relations = {"dependencies": "DEPENDS_ON", "cycles": "DEPENDS_ON", "layers": "DEPENDS_ON",
                         "tables": "ACCESSES", "shared_tables": "ACCESSES",
                         "workflows": "PARTICIPATES_IN", "incidents": "AFFECTED_BY",
                         "call_state": ("CALLS", "WRITES"), "intent_violations": ("WRITES", "SHOULD_NOT_WRITE"),
                         "test_call_links": ("TESTS", "CALLS")}
            for row in record["rows"]:
                for prefix in ("", "other_"):
                    if prefix + "source_key" in row:
                        relation = relations[tool]
                        if isinstance(relation, tuple):
                            relation = relation[bool(prefix)]
                        edge_key = (logical_id(row[prefix + "source_key"]), logical_id(row[prefix + "target_key"]), relation)
                        if edge_key not in self.edge_evidence:
                            raise ValueError("Returned graph relation has no snapshot provenance")
                        row[prefix + "evidence_ids"] = self.edge_evidence[edge_key]
            record["provenance_join"] = {"method": "returned endpoint keys + queried relationship type to immutable edges.json",
                                         "edge_manifest_sha256": self.edge_manifest_sha256}
            record["result_sha256"] = hashlib.sha256(json.dumps(raw, sort_keys=True).encode()).hexdigest()
            record["status"] = "ok"
            if self.layers:
                record["layer_coverage"] = {k: v for k, v in self.layers.status()["layers"].items() if k in REQUIREMENTS[tool]}
            record["row_count"] = len(record["rows"])
            record["limit_note"] = "Exact aggregate over indexed snapshot" if exhaustive else "Bounded sample; missing rows do not prove absence"
            self.cache[key] = record
        except Exception as exc:
            record.update(status="error", error=f"{type(exc).__name__}: {exc}", rows=[])
            raise
        finally:
            record["elapsed_ms"] = round((time.perf_counter() - began) * 1000, 3)
            emit("query.completed" if record["status"] == "ok" else "query.failed",
                 query_id=record["id"], tool=tool, query=query, params=params, status=record["status"],
                 row_count=len(record["rows"]), duration_ms=record["elapsed_ms"],
                 result_sha256=record.get("result_sha256"), evidence_ids=self.evidence_ids(record), error=record.get("error"))
        return record

    def query(self, tool: str, module: str = ""):
        if tool not in QUERIES:
            raise ValueError(f"Unsupported graph tool: {tool}")
        if tool != "hotspots" and module not in self.manifest["modules"] and not (tool in VIEWS and module == ""):
            raise ValueError(f"Unknown module: {module}")
        limit = self.config["graph"]["row_limit"]
        query = QUERIES[tool].format(limit=limit)
        params = {"module": module, **({"layer": VIEWS[tool]} if tool in VIEWS else {})}
        emit("query.requested", tool=tool, query=query, params=params)
        prior = len(self.receipts)
        try:
            self._prepare(tool, module)
        except Exception as exc:
            if len(self.receipts) > prior:
                self.receipts[-1].update(query=query, params=params)
            emit("query.failed", tool=tool, query=query, params=params, phase="preparation", executed=False,
                 query_id=self.receipts[-1]["id"] if len(self.receipts) > prior else None,
                 status="unavailable" if isinstance(exc, LayerUnavailable) else "error", error=f"{type(exc).__name__}: {exc}")
            raise
        return self._execute(tool, query, params, tool in {"inbound_count", "changes"})

    def semantic(self, query: str, modules: list[str] | None, purpose="discovery"):
        if not query.strip() or len(query) > 500:
            raise ValueError("Semantic query must be 1–500 characters")
        if modules is not None and (not modules or len(modules) > 12 or any(m not in self.manifest["modules"] and m != "__documents__" for m in modules)):
            raise ValueError("Semantic scope must contain 1–12 indexed modules/document scope")
        count = min(self.config["investigation"]["top_k"], 10)
        rgql = ("MATCH (d:Chunk) " + ("WHERE d.module IN $modules " if modules is not None else "") +
                "WITH d, vector.cosine(d.embedding, $query_vec) AS score "
                "RETURN d.evidence_id AS evidence_id, d.module AS module, score "
                f"ORDER BY score DESC LIMIT {count}")
        emit("semantic_search.started", search_text=query, modules=modules, purpose=purpose, query=rgql)
        prior = len(self.receipts)
        phase = "preparation"
        try:
            self._prepare("semantic")
            if self.progress:
                self.progress("Searching semantic evidence")
            phase = "embedding"
            began = time.perf_counter()
            encoder = self.manifest["embedding_config"]
            emit("embedding.started", purpose="query", mode=encoder["mode"], model=encoder.get("model"))
            if self.embedder is None:
                # Always use the snapshot's encoder, never silently compare incompatible spaces.
                self.embedder = make_embedder({**self.config, "embedding": encoder})
            method = getattr(self.embedder, "embed_query", self.embedder.embed)
            vector = list(method(query))
            if len(vector) != self.manifest["embedding_dimension"]:
                raise ValueError("Query embedding dimensions differ from snapshot; re-index with the new encoder")
            emit("embedding.completed", purpose="query", dimensions=len(vector), duration_ms=round((time.perf_counter()-began)*1000, 3))
            phase = "query"
            result = self._execute("semantic", rgql, {"modules": modules, "query_vec": vector})
            result["search_text"] = query
            result["purpose"] = purpose
            result["retrieval_mode"] = self.manifest["coverage"]["semantic_retrieval"]
            emit("semantic_search.completed", query_id=result["id"], purpose=purpose, search_text=query,
                 row_count=len(result["rows"]), evidence_ids=self.evidence_ids(result))
            return result
        except Exception as exc:
            if phase == "preparation" and len(self.receipts) > prior:
                self.receipts[-1].update(query=rgql, params={"modules": modules}, search_text=query, purpose=purpose)
            if phase == "embedding":
                emit("embedding.failed", purpose="query", error=f"{type(exc).__name__}: {exc}")
            emit("semantic_search.failed", query=rgql, search_text=query, modules=modules, purpose=purpose,
                 phase=phase, error=f"{type(exc).__name__}: {exc}")
            raise

    def evidence_ids(self, receipt):
        ids = []
        for row in receipt["rows"]:
            for key, value in row.items():
                if key.endswith("evidence_ids") and isinstance(value, list):
                    ids.extend(value)
                elif key == "evidence_id":
                    ids.append(value)
        return list(dict.fromkeys(i for i in ids if i in self.evidence))

    def packet(self, receipts: list[dict], byte_limit: int = 4400):
        # Balance graph observations and both semantic searches. Large result tables
        # must not evict every source passage from a small model context.
        packet = {"queries": [], "passages": [], "omitted_items": 0,
                  "limits": "Rows and excerpts are bounded samples, not evidence of absence. Counts are snapshot-scoped. Full results and layer coverage are in report.json."}

        def fits():
            # Keep a little room for final omission counts.
            return len(json.dumps(packet, ensure_ascii=False).encode()) <= byte_limit - 32

        rows_by_id = {}
        receipts_by_id = {}
        for receipt in receipts:
            compact = {k: receipt[k] for k in ("id", "tool", "status")}
            compact.update(rows=[], rows_omitted=len(receipt["rows"]),
                           scope=receipt.get("params", {}).get("module") or "snapshot or explicit retrieval modules")
            if receipt.get("error"):
                compact["error"] = receipt["error"][:160]
            if "search_text" in receipt:
                compact["purpose"] = receipt.get("purpose", "discovery")
            packet["queries"].append(compact)
            if not fits():
                packet["queries"].pop()
                packet["omitted_items"] += 1 + len(receipt["rows"])
                continue
            rows_by_id[receipt["id"]] = [{k: v for k, v in row.items()
                if not k.endswith("_key") and not k.endswith("evidence_ids") and k != "score"}
                for row in receipt["rows"][:5]]
            receipts_by_id[receipt["id"]] = receipt

        def add_row(query, row):
            query["rows"].append(row)
            if not fits():
                query["rows"].pop()
                return False
            query["rows_omitted"] -= 1
            return True

        # Small exact count aggregates have priority over sampled lists.
        for query in packet["queries"]:
            rows = rows_by_id[query["id"]]
            if len(rows) == 1 and rows[0] and all(isinstance(v, (int, float)) for v in rows[0].values()):
                if add_row(query, rows[0]):
                    rows_by_id[query["id"]] = []

        semantic = [r for r in receipts if r["tool"] == "semantic"]
        candidates = []
        for index in range(2):
            for receipt in semantic:
                ids = self.evidence_ids(receipt)
                if len(ids) > index:
                    candidates.append((ids[index], receipt.get("purpose", "discovery")))
        candidates.extend((eid, "structural") for r in receipts if r["tool"] != "semantic"
                          for eid in self.evidence_ids(r)[:1])
        purposes = {}
        for eid, purpose in candidates:
            purposes.setdefault(eid, [])
            if purpose not in purposes[eid]:
                purposes[eid].append(purpose)
        unique = [(eid, ",".join(roles)) for eid, roles in purposes.items()]
        included = set()

        def add_passage(eid, purpose, text_bytes):
            ev = self.evidence[eid]
            passage = {k: ev[k] for k in ("id", "path", "line_start", "line_end", "kind")}
            excerpt = ev["text"].encode()[:text_bytes].decode("utf-8", errors="ignore")
            passage.update(text=excerpt, excerpt_truncated=len(excerpt) < len(ev["text"]), purpose=purpose)
            packet["passages"].append(passage)
            if not fits():
                packet["passages"].pop()
                return False
            included.add(eid)
            return True

        # Share the available room between the first support and counter witnesses.
        # Exact source text stays intact; truncation and full recorded span are explicit.
        remaining = byte_limit - len(json.dumps(packet, ensure_ascii=False).encode())
        # Keep roughly 40% of remaining space for graph rows as well as the
        # query headers; two excerpts alone must not consume the entire packet.
        excerpt_budget = min(450, max(64, int(remaining * 0.6) // 2 - 250))
        for eid, purpose in unique[:2]:
            add_passage(eid, purpose, excerpt_budget)

        # One row per tool per round prevents a single calls/CFG query taking all space.
        for index in range(5):
            for query in packet["queries"]:
                rows = rows_by_id[query["id"]]
                if index < len(rows):
                    add_row(query, rows[index])
        for eid, purpose in unique:
            if eid not in included:
                add_passage(eid, purpose, 650)
        # Preserve specific collector caveats whenever room remains.
        for query in packet["queries"]:
            receipt = receipts_by_id[query["id"]]
            if receipt.get("layer_coverage"):
                query["limits"] = "; ".join(v["limitation"] for v in receipt["layer_coverage"].values())[:160]
                if not fits():
                    del query["limits"]
        packet["omitted_items"] += sum(q["rows_omitted"] for q in packet["queries"]) + len(unique) - len(included)
        if len(json.dumps(packet, ensure_ascii=False).encode()) > byte_limit:
            raise ValueError("Evidence budget too small")
        return packet
