"""Litigation-specific immutable domain records."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProvenanceKind(str, Enum):
    OBSERVED = "observed"
    EXTRACTED = "extracted"
    INFERRED = "inferred"
    PREDICTED = "predicted"


@dataclass(frozen=True, slots=True)
class CaseDocument:
    source_id: str
    relative_path: str
    media_type: str
    content_sha256: str
    size_bytes: int
    text: str | None
    access_scope: str
    container_source_id: str | None = None

    def __post_init__(self) -> None:
        if not self.source_id or not self.relative_path or not self.access_scope:
            raise ValueError("source_id, relative_path, and access_scope are required")
        if len(self.content_sha256) != 64:
            raise ValueError("content_sha256 must be a SHA-256 hex digest")
        if self.size_bytes < 0:
            raise ValueError("size_bytes cannot be negative")


@dataclass(frozen=True, slots=True)
class StoredEvidence:
    evidence_id: str
    investigation_id: int
    source_id: str
    content_sha256: str
    start_offset: int
    end_offset: int
    provenance_kind: ProvenanceKind
    text: str
    relevance_score: float | None

    def __post_init__(self) -> None:
        if self.start_offset < 0 or self.end_offset < self.start_offset:
            raise ValueError("invalid evidence span")


@dataclass(frozen=True, slots=True)
class DraftReport:
    report_id: str
    investigation_id: int
    title: str
    review_query: str
    status: str
    markdown: str
    evidence_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.status != "draft_for_human_review":
            raise ValueError("reports produced by this package must remain human-review drafts")

