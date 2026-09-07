"""Typed SQLite audit store with read-only inspection."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Mapping

from rfm_platform.documents import EvidenceSpan

from ..models import CaseDocument, DraftReport, ProvenanceKind, StoredEvidence


_SCHEMA_VERSION = 3
_HYPOTHESIS_STATUSES = {
    "proposed",
    "supported",
    "contradicted",
    "inconclusive",
    "query_failed",
}
_QUERY_STATUSES = {"succeeded", "failed"}


class EvidenceStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._migrate()

    def create_investigation(
        self,
        review_query: str,
        access_scope: str,
        *,
        llm_model: str | None = None,
        graph_path: str | Path | None = None,
    ) -> int:
        if not review_query.strip() or not access_scope.strip():
            raise ValueError("review_query and access_scope must be non-empty")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO investigations(
                    review_query, access_scope, status, llm_model, graph_path, created_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    review_query,
                    access_scope,
                    "draft_review",
                    llm_model,
                    str(graph_path) if graph_path is not None else None,
                    self._now(),
                ),
            )
            return int(cursor.lastrowid)

    def add_sources(self, documents: Iterable[CaseDocument]) -> None:
        values = [
            (
                item.source_id,
                item.content_sha256,
                item.relative_path,
                item.media_type,
                item.size_bytes,
                item.access_scope,
                item.container_source_id,
            )
            for item in documents
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT INTO sources(
                    source_id, content_sha256, relative_path, media_type, size_bytes,
                    access_scope, container_source_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source_id, content_sha256) DO UPDATE SET
                    relative_path=excluded.relative_path,
                    media_type=excluded.media_type,
                    size_bytes=excluded.size_bytes,
                    access_scope=excluded.access_scope,
                    container_source_id=excluded.container_source_id
                """,
                values,
            )

    def add_evidence(
        self,
        investigation_id: int,
        evidence: EvidenceSpan,
        provenance_kind: ProvenanceKind = ProvenanceKind.OBSERVED,
    ) -> StoredEvidence:
        if evidence.end_offset < evidence.start_offset:
            raise ValueError("invalid evidence span")
        with self._connect() as connection:
            source = connection.execute(
                "SELECT 1 FROM sources WHERE source_id=? AND content_sha256=?",
                (evidence.source_id, evidence.content_sha256),
            ).fetchone()
            if source is None:
                raise ValueError("evidence source/hash is not registered")
            connection.execute(
                """
                INSERT INTO evidence_items(
                    investigation_id, evidence_id, source_id, content_sha256,
                    start_offset, end_offset, provenance_kind, text, relevance_score, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(investigation_id, evidence_id) DO UPDATE SET
                    relevance_score=MAX(evidence_items.relevance_score, excluded.relevance_score),
                    text=excluded.text
                """,
                (
                    investigation_id,
                    evidence.evidence_id,
                    evidence.source_id,
                    evidence.content_sha256,
                    evidence.start_offset,
                    evidence.end_offset,
                    provenance_kind.value,
                    evidence.text,
                    evidence.score,
                    self._now(),
                ),
            )
        return StoredEvidence(
            evidence_id=evidence.evidence_id,
            investigation_id=investigation_id,
            source_id=evidence.source_id,
            content_sha256=evidence.content_sha256,
            start_offset=evidence.start_offset,
            end_offset=evidence.end_offset,
            provenance_kind=provenance_kind,
            text=evidence.text,
            relevance_score=evidence.score,
        )

    def evidence_for(self, investigation_id: int) -> tuple[StoredEvidence, ...]:
        rows = self.query_readonly(
            """
            SELECT evidence_id, investigation_id, source_id, content_sha256,
                   start_offset, end_offset, provenance_kind, text, relevance_score
            FROM evidence_items WHERE investigation_id=?
            ORDER BY relevance_score DESC, evidence_id
            """,
            (investigation_id,),
        )
        return tuple(self._stored_evidence(row) for row in rows)

    def evidence_for_hypothesis(self, hypothesis_id: str) -> tuple[StoredEvidence, ...]:
        rows = self.query_readonly(
            """
            SELECT e.evidence_id, e.investigation_id, e.source_id, e.content_sha256,
                   e.start_offset, e.end_offset, e.provenance_kind, e.text,
                   e.relevance_score
            FROM evidence_items AS e
            JOIN hypothesis_evidence AS h
              ON h.investigation_id=e.investigation_id AND h.evidence_id=e.evidence_id
            WHERE h.hypothesis_id=?
            ORDER BY e.relevance_score DESC, e.evidence_id
            """,
            (hypothesis_id,),
        )
        return tuple(self._stored_evidence(row) for row in rows)

    def add_hypothesis(
        self,
        *,
        hypothesis_id: str,
        investigation_id: int,
        sequence: int,
        statement: str,
        rationale: str,
        natural_language_query: str,
        analysis_kind: str,
        parent_hypothesis_id: str | None = None,
    ) -> None:
        required = (
            hypothesis_id,
            statement,
            rationale,
            natural_language_query,
            analysis_kind,
        )
        if sequence <= 0 or any(not item.strip() for item in required):
            raise ValueError(
                "hypothesis fields must be non-empty and sequence must be positive"
            )
        now = self._now()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO hypotheses(
                    hypothesis_id, investigation_id, sequence, parent_hypothesis_id,
                    statement, rationale, natural_language_query, analysis_kind,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    hypothesis_id,
                    investigation_id,
                    sequence,
                    parent_hypothesis_id,
                    statement,
                    rationale,
                    natural_language_query,
                    analysis_kind,
                    "proposed",
                    now,
                    now,
                ),
            )

    def set_hypothesis_query(self, hypothesis_id: str, rgql_query: str) -> None:
        if not rgql_query.strip():
            raise ValueError("rgql_query must be non-empty")
        with self._connect() as connection:
            cursor = connection.execute(
                "UPDATE hypotheses SET rgql_query=?, updated_at=? WHERE hypothesis_id=?",
                (rgql_query, self._now(), hypothesis_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown hypothesis: {hypothesis_id}")

    def complete_hypothesis(
        self,
        hypothesis_id: str,
        *,
        status: str,
        assessment: str,
    ) -> None:
        if status not in _HYPOTHESIS_STATUSES or status == "proposed":
            raise ValueError(f"invalid completed hypothesis status: {status}")
        if not assessment.strip():
            raise ValueError("assessment must be non-empty")
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE hypotheses SET status=?, assessment=?, updated_at=?
                WHERE hypothesis_id=?
                """,
                (status, assessment, self._now(), hypothesis_id),
            )
            if cursor.rowcount != 1:
                raise ValueError(f"unknown hypothesis: {hypothesis_id}")

    def record_query_run(
        self,
        *,
        run_id: str,
        investigation_id: int,
        hypothesis_id: str,
        attempt: int,
        natural_language_query: str,
        rgql_query: str,
        requested_runtime: str,
        status: str,
        execution_plan: str | None = None,
        execution_profile: str | None = None,
        planned_device: str | None = None,
        actual_device: str | None = None,
        result: Mapping[str, Any] | None = None,
        error_message: str | None = None,
        query_kind: str = "graph",
    ) -> None:
        if query_kind not in {"graph", "document"}:
            raise ValueError(f"invalid query kind: {query_kind}")
        if status not in _QUERY_STATUSES:
            raise ValueError(f"invalid query status: {status}")
        if attempt <= 0:
            raise ValueError("attempt must be positive")
        if status == "succeeded" and result is None:
            raise ValueError("a successful query run requires a result")
        if status == "failed" and not error_message:
            raise ValueError("a failed query run requires an error message")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO graph_query_runs(
                    run_id, investigation_id, hypothesis_id, attempt,
                    natural_language_query, rgql_query, requested_runtime,
                    planned_device, actual_device, execution_plan, execution_profile,
                    result_json, status, error_message, created_at, query_kind
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    investigation_id,
                    hypothesis_id,
                    attempt,
                    natural_language_query,
                    rgql_query,
                    requested_runtime,
                    planned_device,
                    actual_device,
                    execution_plan,
                    execution_profile,
                    self._json(result) if result is not None else None,
                    status,
                    error_message,
                    self._now(),
                    query_kind,
                ),
            )

    def record_model_interaction(
        self,
        *,
        interaction_id: str,
        investigation_id: int,
        phase: str,
        model: str,
        request: Mapping[str, Any],
        response: Mapping[str, Any],
        hypothesis_id: str | None = None,
    ) -> None:
        required = (interaction_id, phase, model)
        if any(not item.strip() for item in required):
            raise ValueError("model interaction identifiers must be non-empty")
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO model_interactions(
                    interaction_id, investigation_id, hypothesis_id, phase,
                    model, request_json, response_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    interaction_id,
                    investigation_id,
                    hypothesis_id,
                    phase,
                    model,
                    self._json(request),
                    self._json(response),
                    self._now(),
                ),
            )

    def link_hypothesis_evidence(
        self,
        investigation_id: int,
        hypothesis_id: str,
        evidence_ids: Iterable[str],
    ) -> None:
        values = [
            (investigation_id, hypothesis_id, evidence_id)
            for evidence_id in dict.fromkeys(evidence_ids)
        ]
        with self._connect() as connection:
            connection.executemany(
                """
                INSERT OR IGNORE INTO hypothesis_evidence(
                    investigation_id, hypothesis_id, evidence_id
                ) VALUES (?, ?, ?)
                """,
                values,
            )

    def hypotheses_for(self, investigation_id: int) -> tuple[dict[str, Any], ...]:
        return self.query_readonly(
            """
            SELECT hypothesis_id, investigation_id, sequence, parent_hypothesis_id,
                   statement, rationale, natural_language_query, analysis_kind,
                   rgql_query, status, assessment, created_at, updated_at
            FROM hypotheses WHERE investigation_id=?
            ORDER BY sequence
            """,
            (investigation_id,),
        )

    def query_runs_for(self, investigation_id: int) -> tuple[dict[str, Any], ...]:
        return self.query_readonly(
            """
            SELECT run_id, investigation_id, hypothesis_id, attempt,
                   natural_language_query, rgql_query, requested_runtime,
                   planned_device, actual_device, execution_plan, execution_profile,
                   result_json, status, error_message, created_at, query_kind
            FROM graph_query_runs WHERE investigation_id=?
            ORDER BY created_at, attempt
            """,
            (investigation_id,),
        )

    def save_report(self, report: DraftReport) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO reports(
                    report_id, investigation_id, title, review_query, status,
                    markdown, evidence_ids, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    report.report_id,
                    report.investigation_id,
                    report.title,
                    report.review_query,
                    report.status,
                    report.markdown,
                    "\n".join(report.evidence_ids),
                    self._now(),
                ),
            )

    def save_agent_review(self, report, hypotheses):
        """Atomically project the durable agent ledger into the review database."""
        with self._connect() as connection:
            for sequence, h in enumerate(hypotheses, 1):
                connection.execute(
                    "INSERT INTO hypotheses(hypothesis_id,investigation_id,sequence,parent_hypothesis_id,"
                    "statement,rationale,natural_language_query,analysis_kind,status,assessment,created_at,updated_at) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(hypothesis_id) DO UPDATE SET "
                    "statement=excluded.statement,rationale=excluded.rationale,status=excluded.status,"
                    "assessment=excluded.assessment,updated_at=excluded.updated_at",
                    (
                        h["id"],
                        report.investigation_id,
                        sequence,
                        h["parent_id"],
                        h["question"],
                        h["factual_basis"],
                        h["question"],
                        "document",
                        h["status"],
                        json.dumps(h),
                        self._now(),
                        self._now(),
                    ),
                )
            connection.execute(
                "INSERT INTO reports(report_id,investigation_id,title,review_query,status,markdown,evidence_ids,created_at) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(report_id) DO UPDATE SET "
                "markdown=excluded.markdown,evidence_ids=excluded.evidence_ids",
                (
                    report.report_id,
                    report.investigation_id,
                    report.title,
                    report.review_query,
                    report.status,
                    report.markdown,
                    "\n".join(report.evidence_ids),
                    self._now(),
                ),
            )

    def query_readonly(
        self, sql: str, parameters: tuple[Any, ...] = ()
    ) -> tuple[dict[str, Any], ...]:
        normalized = sql.lstrip().upper()
        if not normalized.startswith(("SELECT ", "WITH ", "EXPLAIN ")):
            raise ValueError("runtime SQL inspection is read-only")
        with self._connect(query_only=True) as connection:
            cursor = connection.execute(sql, parameters)
            names = [description[0] for description in cursor.description or ()]
            return tuple(
                dict(zip(names, row, strict=True)) for row in cursor.fetchall()
            )

    def _migrate(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_metadata(
                    version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS investigations(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    review_query TEXT NOT NULL,
                    access_scope TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('draft_review', 'closed')),
                    llm_model TEXT,
                    graph_path TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sources(
                    source_id TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    relative_path TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                    access_scope TEXT NOT NULL,
                    container_source_id TEXT,
                    PRIMARY KEY(source_id, content_sha256)
                );
                CREATE TABLE IF NOT EXISTS evidence_items(
                    investigation_id INTEGER NOT NULL,
                    evidence_id TEXT NOT NULL,
                    source_id TEXT NOT NULL,
                    content_sha256 TEXT NOT NULL,
                    start_offset INTEGER NOT NULL CHECK(start_offset >= 0),
                    end_offset INTEGER NOT NULL CHECK(end_offset >= start_offset),
                    provenance_kind TEXT NOT NULL CHECK(provenance_kind IN ('observed', 'extracted', 'inferred', 'predicted')),
                    text TEXT NOT NULL,
                    relevance_score REAL,
                    created_at TEXT NOT NULL,
                    PRIMARY KEY(investigation_id, evidence_id),
                    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
                    FOREIGN KEY(source_id, content_sha256) REFERENCES sources(source_id, content_sha256)
                );
                CREATE TABLE IF NOT EXISTS reports(
                    report_id TEXT PRIMARY KEY,
                    investigation_id INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    review_query TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status='draft_for_human_review'),
                    markdown TEXT NOT NULL,
                    evidence_ids TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(investigation_id) REFERENCES investigations(id)
                );
                """
            )
            current = connection.execute(
                "SELECT version FROM schema_metadata LIMIT 1"
            ).fetchone()
            if current is None:
                connection.execute(
                    "INSERT INTO schema_metadata(version) VALUES (?)", (2,)
                )
            elif current[0] == 1:
                columns = {
                    row[1]
                    for row in connection.execute(
                        "PRAGMA table_info(investigations)"
                    ).fetchall()
                }
                if "llm_model" not in columns:
                    connection.execute(
                        "ALTER TABLE investigations ADD COLUMN llm_model TEXT"
                    )
                if "graph_path" not in columns:
                    connection.execute(
                        "ALTER TABLE investigations ADD COLUMN graph_path TEXT"
                    )
                connection.execute("UPDATE schema_metadata SET version=?", (2,))
            elif current[0] not in {2, _SCHEMA_VERSION}:
                raise RuntimeError(
                    f"unsupported evidence database schema {current[0]}; expected {_SCHEMA_VERSION}"
                )

            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS hypotheses(
                    hypothesis_id TEXT PRIMARY KEY,
                    investigation_id INTEGER NOT NULL,
                    sequence INTEGER NOT NULL CHECK(sequence > 0),
                    parent_hypothesis_id TEXT,
                    statement TEXT NOT NULL,
                    rationale TEXT NOT NULL,
                    natural_language_query TEXT NOT NULL,
                    analysis_kind TEXT NOT NULL CHECK(analysis_kind IN ('pattern', 'pagerank', 'bfs')),
                    rgql_query TEXT,
                    status TEXT NOT NULL CHECK(status IN ('proposed', 'supported', 'contradicted', 'inconclusive', 'query_failed')),
                    assessment TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(investigation_id, sequence),
                    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
                    FOREIGN KEY(parent_hypothesis_id) REFERENCES hypotheses(hypothesis_id)
                );
                CREATE TABLE IF NOT EXISTS graph_query_runs(
                    run_id TEXT PRIMARY KEY,
                    investigation_id INTEGER NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    attempt INTEGER NOT NULL CHECK(attempt > 0),
                    natural_language_query TEXT NOT NULL,
                    rgql_query TEXT NOT NULL,
                    requested_runtime TEXT NOT NULL,
                    planned_device TEXT,
                    actual_device TEXT,
                    execution_plan TEXT,
                    execution_profile TEXT,
                    result_json TEXT,
                    status TEXT NOT NULL CHECK(status IN ('succeeded', 'failed')),
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(hypothesis_id, attempt),
                    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
                    FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id)
                );
                CREATE TABLE IF NOT EXISTS model_interactions(
                    interaction_id TEXT PRIMARY KEY,
                    investigation_id INTEGER NOT NULL,
                    hypothesis_id TEXT,
                    phase TEXT NOT NULL,
                    model TEXT NOT NULL,
                    request_json TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY(investigation_id) REFERENCES investigations(id),
                    FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id)
                );
                CREATE TABLE IF NOT EXISTS hypothesis_evidence(
                    investigation_id INTEGER NOT NULL,
                    hypothesis_id TEXT NOT NULL,
                    evidence_id TEXT NOT NULL,
                    PRIMARY KEY(hypothesis_id, evidence_id),
                    FOREIGN KEY(investigation_id, evidence_id)
                        REFERENCES evidence_items(investigation_id, evidence_id),
                    FOREIGN KEY(hypothesis_id) REFERENCES hypotheses(hypothesis_id)
                );
                """
            )

        self._migrate_tool_queries()

    def _migrate_tool_queries(self) -> None:
        # SQLite CHECK constraints require a table rebuild. Disable FK enforcement
        # only on this migration connection, preserve names referenced by audit tables,
        # and verify all relationships before committing the transactional rebuild.
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=OFF")
            connection.execute("BEGIN IMMEDIATE")
            version = connection.execute(
                "SELECT version FROM schema_metadata"
            ).fetchone()[0]
            if version == _SCHEMA_VERSION:
                return
            definition = connection.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name='hypotheses'"
            ).fetchone()[0]
            definition = "CREATE TABLE hypotheses_v3 (" + definition.split("(", 1)[1]
            definition = definition.replace(
                "('pattern', 'pagerank', 'bfs')",
                "('pattern', 'pagerank', 'bfs', 'document')",
            )
            connection.execute(definition)
            connection.execute("INSERT INTO hypotheses_v3 SELECT * FROM hypotheses")
            connection.execute("DROP TABLE hypotheses")
            connection.execute("ALTER TABLE hypotheses_v3 RENAME TO hypotheses")
            connection.execute(
                "ALTER TABLE graph_query_runs ADD COLUMN query_kind TEXT NOT NULL "
                "DEFAULT 'graph' CHECK(query_kind IN ('graph', 'document'))"
            )
            violations = connection.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise RuntimeError("evidence migration found broken foreign keys")
            connection.execute(
                "UPDATE schema_metadata SET version=?", (_SCHEMA_VERSION,)
            )

    def _connect(self, query_only: bool = False) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.execute("PRAGMA foreign_keys=ON")
        if query_only:
            connection.execute("PRAGMA query_only=ON")
        return connection

    @staticmethod
    def _stored_evidence(row: Mapping[str, Any]) -> StoredEvidence:
        return StoredEvidence(
            evidence_id=row["evidence_id"],
            investigation_id=row["investigation_id"],
            source_id=row["source_id"],
            content_sha256=row["content_sha256"],
            start_offset=row["start_offset"],
            end_offset=row["end_offset"],
            provenance_kind=ProvenanceKind(row["provenance_kind"]),
            text=row["text"],
            relevance_score=row["relevance_score"],
        )

    @staticmethod
    def _json(value: Mapping[str, Any] | None) -> str:
        return json.dumps(value, sort_keys=True, separators=(",", ":"))

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()
