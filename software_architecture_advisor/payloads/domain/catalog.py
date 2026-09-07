"""Capabilities, dependencies and lazy materialization scope for graph views."""
from dataclasses import dataclass


@dataclass(frozen=True)
class LayerSpec:
    title: str
    dependencies: tuple[str, ...] = ()
    scoped: bool = False
    provider: str = "static"
    limitation: str = "Static extraction is not runtime verification."


LAYERS = {
    "symbols": LayerSpec("Symbol / reference", limitation="Python lexical declarations/references; dynamic name binding unresolved."),
    "dependencies": LayerSpec("Module / dependency"),
    "calls": LayerSpec("Call", ("symbols",), limitation="Resolvable Python names/imports/self methods; unresolved dispatch retained as call sites."),
    "types": LayerSpec("Type / inheritance", ("symbols",), limitation="Explicit bases and annotations; no whole-program type inference."),
    "control_flow": LayerSpec("Control flow", ("symbols",), True, limitation="Intraprocedural statement/branch/loop slices. Exception/finally paths are flagged incomplete."),
    "data_flow": LayerSpec("Data flow", ("symbols",), True, limitation="Flow-insensitive local def-use candidates; no interprocedural or taint proof."),
    "state": LayerSpec("State / mutation", ("symbols",), limitation="SQL literal reads/writes and syntactic attribute mutation; database identity unresolved."),
    "schema": LayerSpec("Database / schema", limitation="Simple CREATE TABLE/REFERENCES declarations and supplied exports; no database introspection."),
    "api": LayerSpec("API / service", ("symbols",), limitation="Literal Python HTTP routes/client calls; runtime availability unknown."),
    "events": LayerSpec("Event / message", ("symbols",), limitation="Literal publish/subscribe call candidates; delivery semantics require supplied evidence."),
    "workflow": LayerSpec("Workflow / state machine", provider="export", limitation="Explicit workflow memberships/transitions; no inferred business state machine."),
    "deployment": LayerSpec("Deployment / topology", provider="declaration", limitation="Compose declarations or explicit export; not observed running topology."),
    "tests": LayerSpec("Test", ("calls",), limitation="Static test-function calls/assertions; not executed test coverage."),
    "git": LayerSpec("Git / co-change", limitation="Frozen HEAD, bounded non-merge commits and current paths; no rename tracking."),
    "ownership": LayerSpec("Ownership", provider="declaration", limitation="CODEOWNERS subset or explicit export; authorship is not ownership."),
    "incidents": LayerSpec("Incident / bug", provider="export", limitation="Explicit incident/issue/PR relationships; causality remains supplied, not independently verified."),
    "configuration": LayerSpec("Configuration / feature flag", ("symbols",), limitation="Declared config keys and getenv references; active production values unknown."),
    "security": LayerSpec("Security / trust boundary", ("symbols",), True, limitation="Syntactic sensitive sink candidates and supplied boundaries; not an exploit or isolation proof."),
    "semantics": LayerSpec("Semantic responsibility", ("symbols",), True, "model", "Cited model inference; never an observed architectural fact."),
    "intent": LayerSpec("Architecture intent", provider="declaration", limitation="Explicit architecture-rules.json or supplied graph; prose ADRs stay source evidence."),
    "embeddings": LayerSpec("Semantic retrieval index", provider="embedding", limitation="Encoder-scoped cosine search; hash mode is only a lexical baseline."),
}

EXPORT_RELATIONS = {
    "symbols": {"DEFINES", "REFERENCES", "USES", "DECLARES", "CONTAINS"},
    "dependencies": {"DEPENDS_ON", "IMPORTS", "USES_LIBRARY", "EXPORTS_TO"},
    "calls": {"CALLS"}, "types": {"IMPLEMENTS", "EXTENDS", "RETURNS", "ACCEPTS_TYPE", "INSTANTIATES"},
    "control_flow": {"NEXT", "BRANCH_TRUE", "BRANCH_FALSE", "EXCEPTION", "LOOP_BACK"},
    "data_flow": {"FLOWS_TO", "DERIVED_FROM", "SANITIZED_BY", "SERIALIZED_TO", "DESERIALIZED_FROM"},
    "state": {"READS", "WRITES", "MUTATES", "DELETES", "CREATES", "ACCESSES"},
    "schema": {"FOREIGN_KEY_TO", "MAPS_TO", "OWNS_DATA", "HAS_COLUMN", "INDEXES"},
    "api": {"CALLS_API", "EXPOSES", "CALLS_SERVICE"}, "events": {"PUBLISHES", "CONSUMES"},
    "workflow": {"PARTICIPATES_IN", "TRANSITIONS_TO", "COMPENSATES", "HAS_STATE"},
    "deployment": {"RUNS_ON", "USES", "DEPLOYED_IN", "DEPENDS_ON"},
    "tests": {"TESTS", "COVERS", "ASSERTS", "USES_FIXTURE", "MOCKS", "VERIFIES_FAILURE"},
    "git": {"CHANGES", "CHANGED_WITH", "RELATED_TO"}, "ownership": {"OWNS", "FREQUENTLY_CHANGES"},
    "incidents": {"AFFECTED_BY", "AFFECTS", "ROOT_CAUSE", "HAS_SYMPTOM", "FIXED_BY", "VERIFIED_BY_TEST", "RELATED_TO"},
    "configuration": {"CONFIGURES", "ENABLES", "BOUND_BY_CONFIG", "READS_CONFIG"},
    "security": {"CROSSES", "AUTHENTICATED_BY", "AUTHORIZED_BY", "CONTAINS_SENSITIVE", "CANDIDATE_SINK"},
    "semantics": {"IMPLEMENTS_CONCEPT", "SHARES_RESPONSIBILITY"},
    "intent": {"SHOULD_DEPEND_ON", "SHOULD_NOT_DEPEND_ON", "SHOULD_OWN", "SHOULD_NOT_WRITE", "SHOULD_BE_STATELESS"},
}


class LayerUnavailable(RuntimeError):
    """A graph capability exists, but its required evidence is not supplied."""
