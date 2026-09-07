"""Declare graph prerequisites for every public query, including cross-view checks."""
REQUIREMENTS = {
    "symbols": ("symbols",), "hotspots": ("dependencies",), "inbound_count": ("dependencies",),
    "dependencies": ("dependencies",), "cycles": ("dependencies",), "blast_radius": ("dependencies",), "layers": ("dependencies",),
    "tables": ("state",), "shared_tables": ("state",), "changes": ("git",), "cochange": ("git",),
    "workflows": ("workflow",), "incidents": ("incidents",), "semantic": ("embeddings",),
    "references": ("symbols",), "calls": ("calls",), "types": ("types",), "control_flow": ("control_flow",),
    "data_flow": ("data_flow",), "state": ("state",), "schema": ("schema",), "api": ("api",), "events": ("events",),
    "workflow_states": ("workflow",), "deployment": ("deployment",), "tests": ("tests",), "ownership": ("ownership",),
    "incident_links": ("incidents",), "configuration": ("configuration",), "security": ("security",),
    "responsibilities": ("semantics",), "intent": ("intent",),
    "call_state": ("calls", "state"), "intent_violations": ("state", "intent"), "test_call_links": ("calls", "tests"),
}

VIEWS = {"references": "symbols", "calls": "calls", "types": "types", "control_flow": "control_flow", "data_flow": "data_flow",
         "state": "state", "schema": "schema", "api": "api", "events": "events", "workflow_states": "workflow",
         "deployment": "deployment", "tests": "tests", "ownership": "ownership", "incident_links": "incidents",
         "configuration": "configuration", "security": "security", "responsibilities": "semantics", "intent": "intent"}

LAYER_QUERIES = {name: ("MATCH (r:EvidenceRelation) WHERE r.layer = $layer AND "
                       "($module = '' OR r.module = $module OR r.target_module = $module) "
                       "RETURN r.source_name AS source, r.relation AS relation, r.target_name AS target, "
                       "r.evidence_ids AS evidence_ids, r.kind AS provenance_kind, r.detail AS detail LIMIT {limit}") for name in VIEWS}
LAYER_QUERIES.update({
    "call_state": "MATCH (a:Symbol)-[:CALLS]->(b:Symbol)-[:WRITES]->(t:Table) WHERE a.module = $module RETURN a.qualified_name AS caller, b.qualified_name AS writer, t.name AS table_name, a.key AS source_key, b.key AS target_key, b.key AS other_source_key, t.key AS other_target_key LIMIT {limit}",
    "intent_violations": "MATCH (a:Module)-[:WRITES]->(t:Table)<-[:SHOULD_NOT_WRITE]-(b:Module) WHERE a.name = $module AND b.name = $module RETURN a.name AS module, t.name AS table_name, a.key AS source_key, t.key AS target_key, b.key AS other_source_key, t.key AS other_target_key LIMIT {limit}",
    "test_call_links": "MATCH (test:Symbol)-[:TESTS]->(f:Symbol)<-[:CALLS]-(caller:Symbol) WHERE f.module = $module RETURN test.qualified_name AS test, f.qualified_name AS function, caller.qualified_name AS caller, test.key AS source_key, f.key AS target_key, caller.key AS other_source_key, f.key AS other_target_key LIMIT {limit}",
})
