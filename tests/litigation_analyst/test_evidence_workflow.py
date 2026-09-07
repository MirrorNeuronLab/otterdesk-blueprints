from pathlib import Path
import sqlite3
import tempfile
import unittest


def analyze_case(folder, query, database, top_k=3):
    return EvidenceAssistant(CaseCorpus(folder), EvidenceStore(database)).analyze(query, top_k=top_k)


FIXTURES = Path(__file__).with_name("fixtures")


class EvidenceWorkflowTests(unittest.TestCase):

    def setUp(self):
        global EvidenceAssistant, CaseCorpus, EvidenceStore
        from domain.evidence.assistant import EvidenceAssistant
        from domain.ingestion import CaseCorpus
        from domain.evidence.store import EvidenceStore
    def test_analysis_persists_exact_citations_and_neutral_draft(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database = root / "review.db"
            report = analyze_case(FIXTURES, "transfer notice", database, top_k=3)
            self.assertEqual(report.status, "draft_for_human_review")
            self.assertGreater(len(report.evidence_ids), 0)
            self.assertIn("SHA-256", report.markdown)
            self.assertIn("human review", report.markdown)
            self.assertNotIn("guilty", report.markdown.casefold())
            stored = EvidenceStore(database).evidence_for(report.investigation_id)
            self.assertEqual(tuple(item.evidence_id for item in stored), report.evidence_ids)
            self.assertTrue(all(item.end_offset >= item.start_offset for item in stored))

    def test_runtime_sql_is_read_only(self):
        with tempfile.TemporaryDirectory() as directory:
            store = EvidenceStore(Path(directory) / "review.db")
            rows = store.query_readonly("SELECT version FROM schema_metadata")
            self.assertEqual(rows[0]["version"], 3)
            with self.assertRaises(ValueError):
                store.query_readonly("DELETE FROM schema_metadata")

    def test_schema_version_one_is_migrated_without_losing_investigations(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory) / "review.db"
            with sqlite3.connect(database) as connection:
                connection.executescript(
                    """
                    CREATE TABLE schema_metadata(version INTEGER NOT NULL);
                    INSERT INTO schema_metadata(version) VALUES (1);
                    CREATE TABLE investigations(
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        review_query TEXT NOT NULL,
                        access_scope TEXT NOT NULL,
                        status TEXT NOT NULL,
                        created_at TEXT NOT NULL
                    );
                    INSERT INTO investigations(
                        review_query, access_scope, status, created_at
                    ) VALUES ('existing review', 'matter-a', 'draft_review', '2026-01-01');
                    """
                )
            store = EvidenceStore(database)
            rows = store.query_readonly(
                "SELECT review_query, llm_model, graph_path FROM investigations"
            )
            self.assertEqual(rows[0]["review_query"], "existing review")
            self.assertIsNone(rows[0]["llm_model"])
            self.assertIsNone(rows[0]["graph_path"])
            self.assertEqual(
                store.query_readonly("SELECT version FROM schema_metadata")[0]["version"],
                3,
            )


if __name__ == "__main__":
    unittest.main()

