from pathlib import Path
import tempfile
import unittest



FIXTURES = Path(__file__).with_name("fixtures")


class GraphProjectionTests(unittest.TestCase):

    def setUp(self):
        global CaseGraphProjector, build_records, CaseCorpus
        from domain.graph_projection import CaseGraphProjector, build_records
        from domain.ingestion import CaseCorpus
    def test_records_are_deterministic_and_provenance_complete(self):
        documents = CaseCorpus(FIXTURES, access_scope="matter-a").scan()
        first = build_records(documents)
        second = build_records(reversed(documents))
        self.assertEqual(first, second)
        nodes, edges = first
        self.assertEqual(len(nodes), 5)
        self.assertEqual(len(edges), 3)
        source_nodes = [node for node in nodes if "SourceArtifact" in node["labels"]]
        self.assertTrue(
            all(
                "content_sha256" in node["properties"]
                for node in source_nodes
                if node["kind"] != "Mailbox"
            )
        )
        self.assertTrue(
            all(node["properties"]["access_scope"] == "matter-a" for node in source_nodes)
        )
        correspondents = [node for node in nodes if node["kind"] == "Correspondent"]
        self.assertEqual(
            {node["properties"]["email"] for node in correspondents},
            {"sender@example.test", "reviewer@example.test"},
        )
        self.assertTrue(
            all(node["properties"]["provenance_kind"] == "extracted" for node in correspondents)
        )
        self.assertEqual({edge["rel_type"] for edge in edges}, {"CONTAINED_IN", "SENT", "TO"})
        extracted_edges = [edge for edge in edges if edge["rel_type"] in {"SENT", "TO", "CC"}]
        self.assertTrue(
            all("content_sha256" in edge["properties"] for edge in extracted_edges)
        )

    def test_existing_graph_is_never_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            graph = Path(directory) / "existing.rgx"
            graph.mkdir()
            projector = CaseGraphProjector(graph, "/missing/rgx")
            with self.assertRaises(FileExistsError):
                projector.project(CaseCorpus(FIXTURES).scan())


if __name__ == "__main__":
    unittest.main()
