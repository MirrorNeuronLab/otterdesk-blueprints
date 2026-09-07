"""Real RGX checks for on-demand lifecycle, provenance and cross-layer semantics."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
from pathlib import Path
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from support import configuration, RGX


class FakeModel:
    calls_count = 0
    def __init__(self, config):
        self.calls = []
    def complete(self, instruction, data):
        type(self).calls_count += 1
        self.calls.append({"status": "ok"})
        return {"concepts": [{"name": "Payment orchestration", "rationale": "Coordinates the supplied worker call.",
                              "evidence_ids": [data["passages"][0]["id"]]}]}


@unittest.skipUnless(RGX.exists(), "Real RGX binary required")
class LazyGraphs(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.repo = self.base / "repo"
        (self.repo / "src").mkdir(parents=True)
        self.write("src/app.py", '''import os
from worker import persist, Base
class Child(Base):
    def update(self, value):
        self.value = value
        return self.value
@router.post('/payments')
def charge(db, value: Base) -> Base:
    transformed = value
    if transformed:
        persist(db, transformed)
    else:
        transformed = None
    requests.post('https://example.test/charge', json=transformed)
    bus.publish('payment.accepted', transformed)
    os.getenv('PAYMENT_MODE')
    return transformed

def risky(text):
    return eval(text)
''')
        self.write("src/worker.py", '''class Base:
    pass

def persist(db, value):
    db.execute('INSERT INTO payments VALUES (?)', (value,))
    return value
''')
        self.write("src/test_app.py", '''from app import charge
from worker import persist

def test_charge():
    assert charge(None, None) is None
    persist(None, None)
''')
        self.write("schema.sql", 'CREATE TABLE payments (\n id INT,\n account_id INT REFERENCES accounts(id)\n);\n')
        self.write("compose.yaml", 'services:\n  api:\n    image: payment:fixture\n    x-advisor-module: app\n    depends_on: [database]\n    networks: [private]\n  database:\n    image: db:fixture\n')
        self.write(".github/CODEOWNERS", '/src/ @platform\n/src/app.py @payments\n')
        self.write("config.json", '{"payment": {"retry": true}}\n')
        self.write("architecture-rules.json", json.dumps({"version": 1, "rules": [{"module": "worker", "relation": "SHOULD_NOT_WRITE", "target": "payments", "rationale": "Only the ledger owns payment writes"}]}))
        self.write("observations.md", 'Fixture workflow and incident export, not production evidence.\n')
        bundle = {"version": 2, "layers": {
            "workflow": {"nodes": [{"key": "workflow:checkout", "kind": "Workflow", "properties": {"name": "checkout"}}],
                         "edges": [self.edge("module:app", "workflow:checkout", "PARTICIPATES_IN")]},
            "incidents": {"nodes": [{"key": "incident:fixture", "kind": "Incident", "properties": {"name": "fixture"}}],
                         "edges": [self.edge("module:app", "incident:fixture", "AFFECTED_BY")]}}}
        self.facts = self.repo / "architecture-facts.json"
        self.facts.write_text(json.dumps(bundle))
        self.cfg = configuration()
        self.cfg["investigation"]["max_queries"] = 100
        self.cfg["graph"]["row_limit"] = 200
        self.workspace = self.base / "output"
        self.git("init")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "baseline")
        self.snapshot()

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, path, text):
        target = self.repo / path
        target.parent.mkdir(exist_ok=True, parents=True)
        target.write_text(text)

    def git(self, *args):
        return subprocess.run(["git", "-C", str(self.repo), *args], check=True, capture_output=True)

    def edge(self, src, dst, kind):
        return {"source": src, "target": dst, "type": kind, "source_path": "observations.md", "line": 1}

    def snapshot(self):
        self.manifest = snapshot_repository(self.repo, self.workspace, self.cfg, self.facts)
        self.directory = self.workspace / "snapshots" / self.manifest["id"]
        self.manager = LayerManager(self.directory, self.cfg)

    def test_capture_calls_no_derived_provider_and_reports_unknown_counts(self):
        with patch("domain.static_layers.Project", side_effect=AssertionError("AST not lazy")), \
             patch("domain.derived_layers.history", side_effect=AssertionError("history not lazy")), \
             patch("domain.derived_layers.CachedEmbedder", side_effect=AssertionError("embeddings not lazy")), \
             patch("domain.derived_layers.JsonModel", side_effect=AssertionError("model not lazy")):
            self.snapshot()
        self.assertEqual(self.manifest["metrics"]["edges"], 0)
        self.assertIsNone(self.manifest["coverage"]["internal_dependency_pairs"])
        self.assertTrue(all(v["status"] == "not_materialized" for v in self.manager.status()["layers"].values()))
        self.assertFalse((self.workspace / "embeddings.sqlite").exists())

    def test_dependency_query_builds_only_dependencies_and_reuses_generation(self):
        session = QuerySession(self.workspace, self.cfg)
        first = session.query("inbound_count", "worker")
        self.assertEqual(first["rows"], [{"inbound_dependency_pairs": 2}])
        self.assertEqual(set(self.manager.current()["entries"]), {"dependencies:*"})
        generation = session.generation
        with patch("domain.static_layers.dependencies", side_effect=AssertionError("rebuilt")):
            second = QuerySession(self.workspace, self.cfg)
            self.assertEqual(second.query("inbound_count", "worker")["rows"], first["rows"])
            self.assertEqual(second.generation, generation)
            self.assertTrue(all(e["cache_hit"] for e in second.materializations))

    def test_all_query_templates_execute_and_every_required_family_is_ready(self):
        FakeModel.calls_count = 0
        session = QuerySession(self.workspace, self.cfg)
        with patch("domain.derived_layers.JsonModel", FakeModel):
            for tool in QUERIES:
                with self.subTest(tool=tool):
                    self.assertEqual(session.query(tool, "app")["status"], "ok")
            session.semantic("payment retry", ["app"])
        self.assertEqual(FakeModel.calls_count, 1)
        status = self.manager.status()
        self.assertEqual(len(status["layers"]), 21)
        self.assertTrue(all(v["status"] == "ready" for v in status["layers"].values()), status)
        for receipt in session.receipts:
            for eid in session.evidence_ids(receipt):
                ev = session.evidence[eid]
                if ev["kind"] != "observed_history":
                    lines = (self.repo / ev["path"]).read_text().splitlines(keepends=True)
                    if "start_offset" not in ev:
                        self.assertEqual(ev["text"], "".join(lines[ev["line_start"]-1:ev["line_end"]]))

    def test_static_cross_graph_paths_and_citations(self):
        session = QuerySession(self.workspace, self.cfg)
        call_state = session.query("call_state", "app")
        self.assertEqual([(r["caller"], r["writer"], r["table_name"]) for r in call_state["rows"]], [("app.charge", "worker.persist", "payments")])
        self.assertEqual({session.evidence[e]["path"] for e in session.evidence_ids(call_state)}, {"src/app.py", "src/worker.py"})
        violated = session.query("intent_violations", "worker")
        self.assertEqual(violated["rows"][0]["table_name"], "payments")
        self.assertEqual({session.evidence[e]["path"] for e in session.evidence_ids(violated)}, {"src/worker.py", "architecture-rules.json"})
        links = session.query("test_call_links", "worker")
        self.assertTrue(any(r["test"] == "test_app.test_charge" and r["caller"] == "app.charge" for r in links["rows"]))
        types = session.query("types", "app")["rows"]
        self.assertTrue(any(r["relation"] == "EXTENDS" and r["target"] == "worker.Base" for r in types))
        self.assertTrue(any(r["relation"] == "PUBLISHES" for r in session.query("events", "app")["rows"]))
        self.assertTrue(any(r["relation"] == "EXPOSES" for r in session.query("api", "app")["rows"]))
        self.assertTrue(any(r["relation"] == "CANDIDATE_SINK" for r in session.query("security", "app")["rows"]))
        self.assertTrue(any(r["relation"] == "FOREIGN_KEY_TO" for r in session.query("schema")["rows"]))
        self.assertEqual([r["source"] for r in session.query("ownership", "app")["rows"]], ["@payments"])
        self.assertTrue(any(r["relation"] == "RUNS_ON" for r in session.query("deployment", "app")["rows"]))

    def test_expensive_slices_are_scoped(self):
        session = QuerySession(self.workspace, self.cfg)
        rows = session.query("control_flow", "app")["rows"]
        self.assertTrue(any(r["relation"] == "BRANCH_TRUE" for r in rows))
        self.assertEqual(set(self.manager.current()["entries"]), {"symbols:*", "control_flow:app"})
        session.query("control_flow", "worker")
        self.assertIn("control_flow:worker", self.manager.current()["entries"])
        session.query("data_flow", "app")
        self.assertNotIn("data_flow:worker", self.manager.current()["entries"])

    def test_missing_evidence_is_unavailable_and_negatively_cached(self):
        self.facts.write_text('{"version":2,"layers":{}}')
        self.snapshot()
        session = QuerySession(self.workspace, self.cfg)
        with self.assertRaises(LayerUnavailable):
            session.query("incidents", "app")
        self.assertEqual(session.receipts[-1]["status"], "unavailable")
        self.assertEqual(self.manager.status()["layers"]["incidents"]["status"], "unavailable")
        with patch.object(LayerManager, "_collect", side_effect=AssertionError("retried absent provider")):
            with self.assertRaises(LayerUnavailable):
                QuerySession(self.workspace, self.cfg).query("incidents", "app")
        self.assertNotIn("incidents:*", self.manager.current()["entries"])

    def test_publication_failure_preserves_previous_graph_and_retries(self):
        self.manager.ensure(["symbols"])
        before = self.manager.current()["id"]
        with patch("domain.lazy.GraphClient.import_json", side_effect=RuntimeError("publication failure")):
            with self.assertRaisesRegex(RuntimeError, "publication failure"):
                self.manager.ensure(["calls"])
        self.assertEqual(self.manager.current()["id"], before)
        self.assertEqual(self.manager.status()["layers"]["calls"]["status"], "failed")
        self.manager.ensure(["calls"])
        self.assertEqual(self.manager.status()["layers"]["calls"]["status"], "ready")

    def test_simultaneous_queries_build_once(self):
        actual = static_layers.dependencies
        count = []
        def slow(*args):
            count.append(True)
            time.sleep(0.08)
            return actual(*args)
        def query():
            return LayerManager(self.directory, self.cfg).ensure(["dependencies"])["id"]
        with patch("domain.static_layers.dependencies", side_effect=slow):
            with ThreadPoolExecutor(2) as pool:
                ids = list(pool.map(lambda _: query(), range(2)))
        self.assertEqual(len(count), 1)
        self.assertEqual(ids[0], ids[1])

    def test_semantic_inference_cached_by_model_and_scope(self):
        FakeModel.calls_count = 0
        with patch("domain.derived_layers.JsonModel", FakeModel):
            session = QuerySession(self.workspace, self.cfg)
            first = session.query("responsibilities", "app")
            self.assertEqual(first["rows"][0]["provenance_kind"], "inferred")
            self.assertTrue(session.evidence_ids(first))
            session.query("responsibilities", "app")
            self.assertEqual(FakeModel.calls_count, 1)
            self.assertNotIn("semantics:worker", self.manager.current()["entries"])
            changed = deepcopy(self.cfg)
            changed["llm"]["model"] = "different-model"
            QuerySession(self.workspace, changed).query("responsibilities", "app")
            self.assertEqual(FakeModel.calls_count, 2)
        self.assertNotIn("embeddings:*", self.manager.current()["entries"])

    def test_semantic_fabricated_evidence_never_publishes(self):
        class BadModel(FakeModel):
            def complete(self, instruction, data):
                return {"concepts": [{"name": "fake", "rationale": "fake", "evidence_ids": ["fabricated"]}]}
        with patch("domain.derived_layers.JsonModel", BadModel):
            with self.assertRaisesRegex(ValueError, "citation"):
                self.manager.ensure(["semantics"], "app")
        self.assertNotIn("semantics:app", self.manager.current()["entries"])

    def test_git_uses_captured_head_and_sources_use_captured_bytes(self):
        self.write("src/app.py", "raise RuntimeError('changed after capture')\n")
        self.git("add", ".")
        self.git("-c", "user.name=Fixture", "-c", "user.email=fixture@example.test", "commit", "-m", "later")
        session = QuerySession(self.workspace, self.cfg)
        self.assertEqual(session.query("changes", "app")["rows"], [{"commits_in_window": 1}])
        self.assertTrue(session.query("call_state", "app")["rows"])
        self.snapshot()
        fresh = QuerySession(self.workspace, self.cfg)
        self.assertEqual(fresh.query("changes", "app")["rows"], [{"commits_in_window": 2}])
        self.assertEqual(fresh.query("call_state", "app")["rows"], [])

    def test_all_twenty_export_capabilities_require_no_external_provider(self):
        layers = {}
        for layer, relations in EXPORT_RELATIONS.items():
            key = "external:" + layer
            layers[layer] = {"nodes": [{"key": key, "kind": "ExternalEvidence", "properties": {"name": layer}}],
                             "edges": [self.edge("module:app", key, sorted(relations)[0])]}
        self.facts.write_text(json.dumps({"version": 2, "layers": layers}))
        self.snapshot()
        with patch.object(LayerManager, "_collect", side_effect=AssertionError("explicit export should be sufficient")):
            for layer in EXPORT_RELATIONS:
                self.manager.ensure([layer], "app")
        current = self.manager.current()
        evidence = json.loads((Path(current["directory"]) / "evidence.json").read_text())
        self.assertTrue(evidence)
        self.assertTrue(all(e["kind"] == "supplied" for e in evidence.values()))
        self.assertTrue(all(self.manager.status()["layers"][layer]["status"] == "ready" for layer in EXPORT_RELATIONS))

    def test_bad_export_provenance_rejected_before_snapshot_changes(self):
        current = (self.workspace / "CURRENT").read_text()
        value = json.loads(self.facts.read_text())
        value["layers"]["incidents"]["edges"][0]["line"] = 99999
        self.facts.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "evidence span"):
            self.snapshot()
        self.assertEqual((self.workspace / "CURRENT").read_text(), current)

    def test_dependency_rebuild_invalidates_materialized_dependents(self):
        self.manager.ensure(["tests"])
        self.assertIn("tests:*", self.manager.current()["entries"])
        changed = deepcopy(self.cfg)
        changed["lazy"]["max_layer_nodes"] += 1
        manager = LayerManager(self.directory, changed)
        manager.ensure(["symbols"])
        self.assertNotIn("calls:*", manager.current()["entries"])
        self.assertNotIn("tests:*", manager.current()["entries"])
        manager.ensure(["tests"])
        self.assertIn("tests:*", manager.current()["entries"])

    def test_scoped_exports_do_not_build_unrequested_module_edges(self):
        self.facts.write_text(json.dumps({"version": 2, "layers": {"control_flow": {
            "nodes": [{"key": "external:block", "kind": "Block", "properties": {"name": "shared"}}],
            "edges": [self.edge("module:app", "external:block", "NEXT"), self.edge("module:worker", "external:block", "NEXT")]}}}))
        self.snapshot()
        self.manager.ensure(["control_flow"], "app")
        active = Path(self.manager.current()["directory"])
        edges = json.loads((active / "edges.json").read_text())
        self.assertEqual(sum(e["rel_type"] == "NEXT" for e in edges), 1)
        self.manager.ensure(["control_flow"], "worker")
        active = Path(self.manager.current()["directory"])
        edges = json.loads((active / "edges.json").read_text())
        self.assertEqual(sum(e["rel_type"] == "NEXT" for e in edges), 2)

    def test_layer_inference_shares_investigation_model_and_budget(self):
        from support import audited_investigate as investigate
        from domain.investigator import offline_assessment
        class BudgetModel(FakeModel):
            def complete(self, instruction, data):
                if len(self.calls) >= 3:
                    raise RuntimeError("Model call budget exhausted")
                self.calls.append({"stage": "semantic" if data.get("semantic_layer") else "investigation"})
                if "candidates" in data:
                    return {"hypotheses": [{"module": "app", "family": "responsibility", "statement": "app may mix responsibilities",
                        "semantic_query": "payment orchestration", "counter_query": "cohesive intentional orchestration"}]}
                if data.get("semantic_layer"):
                    return {"concepts": [{"name": "Payment orchestration", "rationale": "Observed worker calls", "evidence_ids": [data["passages"][0]["id"]]}]}
                return offline_assessment({"module": "app", "family": "responsibility"}, data["packet"])
        model = BudgetModel(self.cfg)
        with patch("domain.derived_layers.JsonModel", side_effect=AssertionError("must reuse investigation model")):
            report = investigate(self.workspace, self.cfg, "Inspect app responsibilities", model=model)
        self.assertEqual(report["metrics"]["llm_calls"], 3)
        self.assertEqual(report["metrics"]["layer_model_calls"], 1)
        self.assertEqual(report["status"], "failed")
        self.assertTrue(any("budget" in e for e in report["errors"]))

    def test_planner_can_reach_every_graph_family(self):
        from domain.investigator import FAMILIES
        from domain.query_catalog import REQUIREMENTS
        reachable = {layer for tools in FAMILIES.values() for tool in tools for layer in REQUIREMENTS[tool]}
        self.assertEqual(reachable, set(LAYERS) - {"embeddings"})

    def test_unavailable_runtime_view_yields_inconclusive_actionable_report(self):
        from support import audited_investigate as investigate
        from domain.investigator import offline_assessment
        self.facts.write_text('{"version":2,"layers":{}}')
        self.snapshot()
        class Model(FakeModel):
            def complete(self, instruction, data):
                self.calls.append({"stage": "test"})
                if "candidates" in data:
                    return {"hypotheses": [{"module": "app", "family": "workflow", "statement": "app may violate workflow transitions",
                        "semantic_query": "payment workflow", "counter_query": "intentional workflow coordinator"}]}
                result = offline_assessment({"module": "app", "family": "workflow"}, data["packet"])
                result["verdict"] = "supported"
                return result
        report = investigate(self.workspace, self.cfg, "Inspect app workflow", model=Model(self.cfg))
        self.assertEqual(report["status"], "review_draft", report["errors"])
        self.assertEqual(report["findings"][0]["assessment"]["verdict"], "inconclusive")
        self.assertEqual(report["decision"]["verdict"], "inconclusive")
        self.assertTrue(any("workflow" in e for e in report["decision"]["missing_evidence"]))
        self.assertTrue(any(q["status"] == "unavailable" for q in report["queries"]))
        self.assertTrue(report["decision"]["next_action"])

    def test_warm_queries_do_not_wait_for_an_unrelated_cold_build(self):
        self.manager.ensure(["dependencies"])
        with ThreadPoolExecutor(1) as pool:
            with self.manager.lock():
                future = pool.submit(lambda: QuerySession(self.workspace, self.cfg).query("inbound_count", "worker"))
                result = future.result(timeout=1)
        self.assertEqual(result["rows"], [{"inbound_dependency_pairs": 2}])

import pytest
from support import ROOT, RGX, configuration, audited_investigate

@pytest.fixture(autouse=True)
def bind_domain(architecture_paths):
    global LAYERS, EXPORT_RELATIONS, LayerUnavailable, QuerySession, QUERIES, snapshot_repository, LayerManager, static_layers
    from domain.catalog import LAYERS, EXPORT_RELATIONS, LayerUnavailable
    from domain.graph import QuerySession, QUERIES
    from domain.ingest import snapshot_repository
    from domain.lazy import LayerManager
    from domain import static_layers
