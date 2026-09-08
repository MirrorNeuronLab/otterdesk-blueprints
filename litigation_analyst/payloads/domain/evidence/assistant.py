"""Evidence-oriented analysis with exact citations and neutral draft output."""

from __future__ import annotations

import hashlib
from typing import Iterable, Mapping

from mn_sdk_rag import DocumentIndex, EvidenceSpan

from ..models import CaseDocument, DraftReport, ProvenanceKind, StoredEvidence
from ..ingestion.corpus import CaseCorpus
from .store import EvidenceStore


class EvidenceAssistant:
    def __init__(
        self,
        corpus: CaseCorpus,
        store: EvidenceStore,
        index: DocumentIndex | None = None,
    ) -> None:
        self.corpus = corpus
        self.store = store
        self.index = index or DocumentIndex()

    def analyze(
        self,
        review_query: str,
        top_k: int = 10,
        title: str = "Evidence Review Draft",
    ) -> DraftReport:
        if not review_query.strip():
            raise ValueError("review_query must be non-empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        documents = self.corpus.scan()
        self.store.add_sources(documents)
        self.corpus.inject(self.index)
        investigation_id = self.store.create_investigation(
            review_query, self.corpus.access_scope
        )
        stored = self.capture_evidence(
            investigation_id,
            review_query,
            top_k=top_k,
            documents=documents,
        )
        report_id = hashlib.sha256(
            f"{investigation_id}|{review_query}|{'|'.join(item.evidence_id for item in stored)}".encode(
                "utf-8"
            )
        ).hexdigest()[:24]
        report = DraftReport(
            report_id=report_id,
            investigation_id=investigation_id,
            title=title,
            review_query=review_query,
            status="draft_for_human_review",
            markdown=self._render(title, review_query, stored),
            evidence_ids=tuple(item.evidence_id for item in stored),
        )
        self.store.save_report(report)
        return report

    def capture_evidence(
        self,
        investigation_id: int,
        query: str,
        *,
        top_k: int,
        documents: Iterable[CaseDocument] | Mapping[str, CaseDocument] | None = None,
    ) -> tuple[StoredEvidence, ...]:
        """Search, verify exact spans, and persist evidence for an existing investigation."""

        if not query.strip():
            raise ValueError("query must be non-empty")
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if documents is None:
            scanned = self.corpus.scan()
            document_map = {item.source_id: item for item in scanned}
        elif isinstance(documents, Mapping):
            document_map = dict(documents)
        else:
            document_map = {item.source_id: item for item in documents}
        stored: list[StoredEvidence] = []
        for item in self.index.search(
            query,
            top_k=top_k,
            access_scope=self.corpus.access_scope,
        ):
            self._validate_evidence(item, document_map)
            stored.append(
                self.store.add_evidence(
                    investigation_id,
                    item,
                    provenance_kind=ProvenanceKind.OBSERVED,
                )
            )
        return tuple(stored)

    @staticmethod
    def _validate_evidence(
        evidence: EvidenceSpan, documents: dict[str, CaseDocument]
    ) -> None:
        document = documents.get(evidence.source_id)
        if document is None or document.text is None:
            raise ValueError(f"evidence source is not in the indexed corpus: {evidence.source_id}")
        if document.content_sha256 != evidence.content_sha256:
            raise ValueError(f"evidence hash mismatch: {evidence.source_id}")
        exact = document.text[evidence.start_offset : evidence.end_offset]
        if exact != evidence.text:
            raise ValueError(f"evidence span mismatch: {evidence.evidence_id}")

    @staticmethod
    def _render(title: str, review_query: str, evidence) -> str:
        lines = [
            f"# {title}",
            "",
            "**Status:** Draft for human review",
            "",
            "## Review request",
            "",
            review_query,
            "",
            "## Method",
            "",
            "The corpus was content-hashed, divided into exact source spans, and ranked with "
            "the configured retrieval index. Scores below describe retrieval similarity only; "
            "they do not measure truth, intent, liability, culpability, or admissibility.",
            "",
            "## Retrieved source passages",
            "",
        ]
        if not evidence:
            lines.extend(
                [
                    "No source passage was returned for this review request. No factual or "
                    "legal conclusion can be drawn from an empty result.",
                    "",
                ]
            )
        for position, item in enumerate(evidence, start=1):
            score = "not recorded" if item.relevance_score is None else f"{item.relevance_score:.6f}"
            lines.extend(
                [
                    f"### Evidence {position}",
                    "",
                    f"- Evidence ID: `{item.evidence_id}`",
                    f"- Source ID: `{item.source_id}`",
                    f"- SHA-256: `{item.content_sha256}`",
                    f"- Character span: `{item.start_offset}:{item.end_offset}`",
                    f"- Provenance: `{item.provenance_kind.value}`",
                    f"- Retrieval score: `{score}`",
                    "",
                    *[f"> {line}" if line else ">" for line in item.text.splitlines()],
                    "",
                ]
            )
        lines.extend(
            [
                "## Review limitations",
                "",
                "This draft reports retrieved passages only. A qualified reviewer must assess "
                "context, completeness, privilege, authenticity, admissibility, and any legal "
                "interpretation before use.",
                "",
            ]
        )
        return "\n".join(lines)
