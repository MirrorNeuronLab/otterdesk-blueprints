"""Bind installed skill APIs to this case's authorized immutable artifacts."""

import json
import re

from mn_document_reading_skill import extract_outline
from mn_document_reading_skill.search import PassageIndex
from mn_graph_analysis_skill import GraphClient
from mn_pdf_extract_skill import extract_pages_from_pdf
from mn_prototype_bounded_tool_loop_agent.skills import SkillRuntime
from rfm_platform.documents import EvidenceSpan

from ..evidence.assistant import EvidenceAssistant
from ..indexing import digest

DOC = "mirrorneuron.document.reading"
GRAPH = "mirrorneuron.graph.analysis"
PDF = "mirrorneuron.pdf.extract"


def bind_skills(case, corpus, store, investigation_id, declared):
    documents = {d.source_id: d for d in corpus.scan()}
    index = PassageIndex(case / "documents.sqlite3", corpus.access_scope)
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
        return verified(index.search(query, top_k))

    def passage(evidence_id):
        return verified(index.passage(evidence_id))

    def query(rgql, params=None):
        # The complete graph is case-scoped; the model cannot supply another database.
        masked = re.sub(r"'(?:[^'\\]|\\.)*'", "''", rgql)
        limits = re.findall(r"\bLIMIT\s+(\d+)\b", masked, re.I)
        if not limits or any(not 1 <= int(n) <= 50 for n in limits):
            raise ValueError("graph queries require literal LIMIT in 1..50")
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

    bindings = {
        (DOC, "search"): search,
        (DOC, "sources"): index.sources,
        (DOC, "read_source"): lambda **args: verified(index.read_source(**args)),
        (DOC, "decode_rot13"): lambda **args: verified(index.decode_rot13(**args)),
        (DOC, "summarize_csv"): lambda **args: verified(index.summarize_csv(**args)),
        (DOC, "passage"): passage,
        (DOC, "outline"): extract_outline,
        (GRAPH, "query"): query,
        (PDF, "extract_pages"): pdf,
    }
    return SkillRuntime.discover(declared, bindings)
