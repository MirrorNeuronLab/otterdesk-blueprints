"""Dependency-aware lazy graph publication with cross-process single-flight builds."""
from contextlib import contextmanager
import fcntl
import json
from pathlib import Path
import time
from uuid import uuid4

from mn_graph_analysis_skill import GraphClient
from .catalog import LAYERS, LayerUnavailable
from .events import emit
from .ingest import digest
from .records import Records, add_export
from . import static_layers as static
from . import derived_layers as derived

COLLECTOR_VERSION = "multi-graph/2"


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(value, sort_keys=True))
    temporary.replace(path)


class LayerManager:
    def __init__(self, directory, config, model=None, progress=None):
        self.directory, self.config = Path(directory), config
        self.manifest = json.loads((self.directory / "manifest.json").read_text())
        if self.manifest.get("format_version") != 2:
            raise ValueError("This snapshot predates lazy graphs; re-ingest to enable multi-graph queries. Existing reports remain readable.")
        self.root = self.directory / "layers"
        self.root.mkdir(exist_ok=True)
        self.sources = None
        self.project = None
        self.events = []
        self.model = model
        self.progress = progress
        self.announced = set()

    @contextmanager
    def lock(self):
        with (self.root / "build.lock").open("a") as file:
            deadline = time.monotonic() + self.config.get("lazy", {}).get("lock_timeout_seconds", 120)
            waiting = False
            while True:
                try:
                    fcntl.flock(file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    if not waiting and self.progress:
                        emit("graph.lock.waiting")
                        self.progress("Waiting for another graph build to finish")
                        waiting = True
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Timed out waiting for a graph materialization")
                    time.sleep(0.025)
            try:
                yield
            finally:
                fcntl.flock(file.fileno(), fcntl.LOCK_UN)

    def current(self):
        pointer = self.root / "CURRENT"
        if not pointer.exists():
            return {"id": "base", "entries": {}, "directory": str(self.directory)}
        name = pointer.read_text().strip()
        if not name.isalnum():
            raise ValueError("Invalid graph generation pointer")
        directory = self.root / "generations" / name
        value = json.loads((directory / "generation.json").read_text())
        value["directory"] = str(directory)
        return value

    def status(self):
        current = self.current()
        attempts = json.loads((self.root / "attempts.json").read_text()) if (self.root / "attempts.json").exists() else {}
        result = {}
        for layer, spec in LAYERS.items():
            scopes = {key.split(":", 1)[1]: {"status": "ready", "fingerprint": value["fingerprint"], "details": value["details"]}
                      for key, value in current["entries"].items() if value["layer"] == layer}
            for key, value in attempts.items():
                if key.startswith(layer + ":") and key.split(":", 1)[1] not in scopes:
                    scopes[key.split(":", 1)[1]] = value
            states = [v["status"] for v in scopes.values()]
            result[layer] = {"title": spec.title, "provider": spec.provider, "scope": "module" if spec.scoped else "snapshot",
                             "dependencies": list(spec.dependencies), "status": "ready" if "ready" in states else (states[-1] if states else "not_materialized"),
                             "scopes": scopes, "limitation": spec.limitation}
        return {"snapshot": self.manifest["id"], "generation": current["id"], "layers": result}

    def _fingerprint(self, layer, scope, dependencies):
        recipe = {"snapshot": self.manifest["id"], "collector": COLLECTOR_VERSION, "layer": layer, "scope": scope,
                  "dependencies": dependencies, "options": self.config.get("lazy", {})}
        if layer == "semantics":
            recipe["model"] = self.config["llm"]
        if layer == "embeddings":
            recipe["encoder"] = self.manifest["embedding_config"]
        return digest(json.dumps(recipe, sort_keys=True).encode())

    def _cached(self, current, requirements, module):
        # Existing immutable generations can serve warm reads during another build.
        events, checked = [], set()
        def valid(layer):
            if layer not in LAYERS:
                return False
            spec = LAYERS[layer]
            scope = module if spec.scoped else "*"
            key = layer + ":" + scope
            if spec.scoped and module not in self.manifest["modules"]:
                return False
            if key in checked:
                return True
            entry = current["entries"].get(key)
            if not entry or not all(valid(d) for d in spec.dependencies):
                return False
            dependencies = {d + ":" + (scope if LAYERS[d].scoped else "*"): current["entries"][d + ":" + (scope if LAYERS[d].scoped else "*")]["fingerprint"] for d in spec.dependencies}
            if entry["fingerprint"] != self._fingerprint(layer, scope, dependencies):
                return False
            checked.add(key)
            events.append({"layer": layer, "scope": scope, "cache_hit": True, "build_ms": 0})
            return True
        return events if all(valid(layer) for layer in requirements) else None

    def _reused(self, layer, scope):
        emit("graph.cache_hit", layer=layer, scope=scope)
        if (layer, scope) not in self.announced:
            if self.progress:
                self.progress(f"Reusing graph: {layer} ({scope})")
            self.announced.add((layer, scope))

    def ensure(self, requirements, module=""):
        self.events = []
        current = self.current()
        cached = self._cached(current, requirements, module)
        if cached is not None:
            self.events = cached
            for event in cached:
                self._reused(event["layer"], event["scope"])
            return current
        with self.lock():
            for layer in requirements:
                self._ensure(layer, module, set())
        return self.current()

    def _ensure(self, layer, module, visiting):
        if layer not in LAYERS:
            raise ValueError(f"Unknown graph layer: {layer}")
        spec = LAYERS[layer]
        scope = module if spec.scoped else "*"
        if spec.scoped and module not in self.manifest["modules"]:
            raise ValueError(f"{layer} requires one indexed module")
        key = layer + ":" + scope
        if key in visiting:
            raise ValueError("Graph layer dependency cycle")
        visiting.add(key)
        for dependency in spec.dependencies:
            self._ensure(dependency, module, visiting)
        visiting.remove(key)
        current = self.current()
        dependencies = {d + ":" + (scope if LAYERS[d].scoped else "*"): current["entries"][d + ":" + (scope if LAYERS[d].scoped else "*")]["fingerprint"] for d in spec.dependencies}
        fingerprint = self._fingerprint(layer, scope, dependencies)
        if current["entries"].get(key, {}).get("fingerprint") == fingerprint:
            self.events.append({"layer": layer, "scope": scope, "cache_hit": True, "build_ms": 0})
            self._reused(layer, scope)
            return
        attempts_path = self.root / "attempts.json"
        attempts = json.loads(attempts_path.read_text()) if attempts_path.exists() else {}
        if attempts.get(key, {}).get("status") == "unavailable" and attempts[key].get("fingerprint") == fingerprint:
            emit("graph.unavailable", layer=layer, scope=scope, cached=True, error=attempts[key]["error"])
            raise LayerUnavailable(attempts[key]["error"])
        attempts[key] = {"status": "building", "fingerprint": fingerprint, "started_at": time.time()}
        atomic_json(attempts_path, attempts)
        began = time.perf_counter()
        emit("graph.build.started", layer=layer, scope=scope, dependencies=list(dependencies), fingerprint=fingerprint)
        try:
            if self.progress:
                self.progress(f"Building graph: {layer} ({scope})")
            if self.sources is None:
                self.sources = json.loads((self.directory / "sources.json").read_text())
            active = Path(current["directory"])
            known_nodes = {n["id"]: n for n in json.loads((active / "nodes.json").read_text())}
            known_edges = json.loads((active / "edges.json").read_text())
            known_evidence = json.loads((active / "evidence.json").read_text())
            records = Records(self.sources, layer, scope, known_nodes)
            records.details["limitations"].append(spec.limitation)
            bundle = json.loads((self.directory / "graph-inputs.json").read_text())
            exported = add_export(records, bundle, self.manifest["modules"])
            if not (bundle["version"] == 2 and exported is not None) and not (spec.provider == "export" and exported):
                self._collect(records, layer, scope, known_edges)
            if spec.provider == "export" and not exported and not (bundle["version"] == 2 and layer in bundle.get("layers", {})):
                raise LayerUnavailable(f"{layer} requires an explicit version-2 {layer} graph export with source provenance")
            value = records.finish()
            for eid in {eid for e in value["edges"] for eid in e["properties"]["evidence_ids"]}:
                if eid not in value["evidence"]:
                    if eid not in known_evidence:
                        raise ValueError("Layer references unknown evidence")
                    value["evidence"][eid] = known_evidence[eid]
            self._validate_size(value)
            record_file = self.root / "records" / (fingerprint + ".json")
            record_file.parent.mkdir(exist_ok=True)
            atomic_json(record_file, value)
            entry = {"layer": layer, "scope": scope, "fingerprint": fingerprint, "dependencies": dependencies,
                     "records": str(record_file.relative_to(self.root)), "record_sha256": digest(record_file.read_bytes()),
                     "details": {k: v for k, v in value["details"].items() if k not in {"model_trace", "raw_log"}},
                     "built_at": time.time()}
            entries = dict(current["entries"])
            entries[key] = entry
            # Invalidate dependent projections when a collector/config version changes.
            changed = True
            while changed:
                changed = False
                for candidate, prior in list(entries.items()):
                    if candidate == key:
                        continue
                    if any(d not in entries or entries[d]["fingerprint"] != expected for d, expected in prior["dependencies"].items()):
                        del entries[candidate]
                        changed = True
            self._publish(entries)
            self.announced.add((layer, scope))
            if self.progress:
                self.progress(f"Graph ready: {layer} ({scope})")
            attempts.pop(key, None)
            atomic_json(attempts_path, attempts)
            self.events.append({"layer": layer, "scope": scope, "cache_hit": False, "build_ms": round((time.perf_counter()-began)*1000, 3),
                                "model_calls": value["details"].get("model_calls", 0)})
            emit("graph.build.completed", **self.events[-1])
        except Exception as exc:
            attempts[key] = {"status": "unavailable" if isinstance(exc, LayerUnavailable) else "failed", "fingerprint": fingerprint,
                             "error": f"{type(exc).__name__}: {exc}", "finished_at": time.time()}
            atomic_json(attempts_path, attempts)
            if self.progress:
                self.progress(f"Graph {attempts[key]['status']}: {layer} ({scope})")
            self.events.append({"layer": layer, "scope": scope, "cache_hit": False, "status": attempts[key]["status"], "error": str(exc)})
            emit("graph.build.failed", **self.events[-1])
            raise

    def _collect(self, records, layer, scope, known_edges):
        needs_project = layer in {"symbols", "dependencies", "calls", "types", "state", "control_flow", "data_flow", "api", "events", "tests", "configuration", "security"}
        if needs_project and self.project is None:
            self.project = static.Project(self.sources, self.manifest["modules"])
        if layer in {"symbols", "dependencies", "calls", "types", "state"}:
            getattr(static, layer)(records, self.project)
        elif layer in {"control_flow", "data_flow"}:
            getattr(static, layer)(records, self.project, scope)
        elif layer in {"api", "events", "security"}:
            static.api_events_security(records, self.project, layer, scope)
        elif layer == "tests":
            static.tests(records, self.project, known_edges)
        elif layer == "schema":
            derived.schema(records)
        elif layer == "git":
            derived.history(records, self.manifest)
        elif layer == "ownership":
            derived.ownership(records, self.manifest["modules"])
        elif layer == "deployment":
            derived.deployment(records)
        elif layer == "configuration":
            derived.configuration(records, self.project)
        elif layer == "intent":
            derived.intent(records, self.manifest["modules"])
        elif layer == "embeddings":
            derived.embeddings(records, self.manifest, self.config, self.directory.parents[1] / "embeddings.sqlite")
        elif layer == "semantics":
            derived.semantics(records, self.manifest, self.config, scope, self.model)

    def _validate_size(self, value):
        cfg = self.config.get("lazy", {})
        if len(value["nodes"]) > cfg.get("max_layer_nodes", 200000) or len(value["edges"]) > cfg.get("max_layer_edges", 400000):
            raise ValueError("Layer materialization exceeded configured node/edge budget")

    def _publish(self, entries):
        nodes = {n["id"]: n for n in json.loads((self.directory / "nodes.json").read_text())}
        edges, evidence = {}, {}
        for name, entry in sorted(entries.items()):
            raw = (self.root / entry["records"]).read_bytes()
            if digest(raw) != entry["record_sha256"]:
                raise ValueError("Materialized graph records failed integrity verification")
            value = json.loads(raw)
            for node in value["nodes"]:
                if node["id"] in nodes:
                    prior = nodes[node["id"]]
                    if prior["properties"]["key"] != node["properties"]["key"] or prior["kind"] != node["kind"]:
                        raise ValueError("Node identity collision")
                    node["properties"] = {**prior["properties"], **node["properties"]}
                nodes[node["id"]] = node
            for edge in value["edges"]:
                if edge["id"] in edges:
                    existing = edges[edge["id"]]
                    if any(existing[k] != edge[k] for k in ("src", "dst", "rel_type")):
                        raise ValueError("Edge identity collision")
                    existing["properties"]["evidence_ids"] = sorted(set(existing["properties"]["evidence_ids"] + edge["properties"]["evidence_ids"]))
                else:
                    edges[edge["id"]] = edge
            evidence.update(value["evidence"])
        for edge in edges.values():
            if edge["src"] not in nodes or edge["dst"] not in nodes:
                raise ValueError("Missing graph endpoint during publication")
        generation = uuid4().hex
        directory = self.root / "generations" / generation
        directory.mkdir(parents=True)
        for filename, value in (("nodes.json", list(nodes.values())), ("edges.json", list(edges.values())), ("evidence.json", evidence)):
            (directory / filename).write_text(json.dumps(value))
        client = GraphClient(directory / "graph.rgx", self.config["graph"]["binary"], self.config["graph"]["timeout_seconds"])
        emit("graph.publication.started", generation=generation, nodes=len(nodes), edges=len(edges))
        client.import_json(directory / "nodes.json", directory / "edges.json")
        emit("graph.integrity_check.started", generation=generation)
        client.check()
        emit("graph.integrity_check.completed", generation=generation)
        atomic_json(directory / "generation.json", {"id": generation, "entries": entries})
        pointer = self.root / ("current-" + generation + ".tmp")
        pointer.write_text(generation)
        pointer.replace(self.root / "CURRENT")
        emit("graph.publication.completed", generation=generation)
