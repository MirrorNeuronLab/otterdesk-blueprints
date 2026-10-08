"""Bind installed skill APIs to this case's authorized immutable artifacts."""

import json
from dataclasses import asdict
from mn_graph_analysis_skill import GraphClient, ensure_bounded_readonly_rgql
from mn_docs_to_markdown_skill import extract_pages_from_pdf
from mn_prototype_bounded_tool_loop_agent.skills import SkillRuntime
from mn_sdk_rag import EvidenceSpan

from ..evidence.assistant import EvidenceAssistant
from ..indexing import digest
from .evidence_tools import descriptor

DOC = "otterdesk.litigation.evidence"
GRAPH = "mirrorneuron.graph.analysis"
PDF = DOC


def bind_skills(case, corpus, store, investigation_id, declared, *, config=None, scope=None):
    documents = {d.source_id: d for d in corpus.scan()}
    graph = GraphClient(
        case / "evidence.rgx", timeout_seconds=30, max_output_bytes=60000
    )
    inventory = json.loads((case / "source_inventory.json").read_text())

    def verified(result):
        for item in result["passages"]:
            span = EvidenceSpan(**item, provenance_kind="observed")
            EvidenceAssistant._validate_evidence(span, documents)
            store.add_evidence(investigation_id, span)
        return result

    def search(query, top_k=3):
        from ..source_query import search as source_search
        if config is None or scope is None:
            raise ValueError("Case evidence search requires its configured source scope")
        return verified(source_search(case, corpus, config, scope, query, top_k))

    def passage(evidence_id):
        record = next((e for e in store.evidence_for(investigation_id) if e.evidence_id == evidence_id), None)
        if record is None:
            raise ValueError('unknown case evidence ID')
        span = asdict(record)
        span.pop('investigation_id'); span.pop('provenance_kind'); span.pop('relevance_score')
        return verified({'passages': [span], 'exhaustive': False})

    def query(rgql, params=None):
        # The complete graph is case-scoped; the model cannot supply another database.
        ensure_bounded_readonly_rgql(rgql, max_limit=50)
        result = graph.query(rgql, params)
        return {
            "result": result,
            "provenance": "observed_graph_query",
            "note": "Interpretation is inferred. Retrieve exact document passages to substantiate findings.",
        }

    def pdf(source_id):
        document = documents.get(source_id)
        if document is None or document.media_type != "application/pdf":
            raise ValueError("unknown authorized PDF source ID")
        record = next(
            r for r in inventory["files"] if r["path"] == document.relative_path
        )
        path = case / "originals" / record["sha256"]
        if path.is_symlink() or digest(path) != record["sha256"]:
            raise ValueError("original PDF hash mismatch")
        return {
            "pages": extract_pages_from_pdf(path),
            "note": "For citations use normalized indexed passage IDs; these page results are extraction observations.",
        }

    def temporal_projection():
        from ..temporal_evidence import project
        return project(tuple(documents.values()), inventory["repository_id"])

    def temporal_paths(seeds, target=None):
        from ..temporal_evidence import paths
        result = paths(temporal_projection(), seeds, corpus.access_scope, target=target)
        refs = {r['evidence_id']: r for p in result['paths'] + result['partial_paths']
                for edge in p['edges'] for r in edge['evidence_refs']}
        return verified({**result, 'passages': list(refs.values()), 'exhaustive': not result['unresolved']})

    def compare_event_order(earlier_id, later_id):
        from ..temporal_evidence import compare
        result = compare(temporal_projection(), earlier_id, later_id)
        refs = {r['evidence_id']: r for r in result['evidence_refs']}
        return verified({**result, 'passages': list(refs.values()), 'exhaustive': False})

    def chronology():
        result = temporal_projection()
        refs = {r['evidence_id']: r for event in result['events'] for r in event['evidence_refs']}
        return verified({**result, 'passages': list(refs.values()), 'exhaustive': False,
            'qualification': 'Email Date headers only; other event lanes have not been extracted.'})

    bindings = {
        (DOC, "search"): search,
        (DOC, "passage"): passage,
        (GRAPH, "query"): query,
        (PDF, "extract_pages"): pdf,
        (DOC, "temporal_paths"): temporal_paths,
        (DOC, "compare_event_order"): compare_event_order,
        (DOC, "chronology"): chronology,
    }
    if "mirrorneuron-docs-to-markdown-skill" not in declared:
        raise ValueError("Case document tools require the declared docs-to-markdown skill")
    if "mirrorneuron-temporal-graph-skill" not in declared:
        raise ValueError("Case temporal tools require the declared temporal graph skill")
    graph_runtime = SkillRuntime.discover(
        [name for name in declared if name not in {"mirrorneuron-docs-to-markdown-skill", "mirrorneuron-temporal-graph-skill"}],
        {(GRAPH, "query"): query},
    )
    return SkillRuntime([*graph_runtime.descriptors.values(), descriptor()], bindings)
