from pathlib import Path
import unittest

from rfm_platform.documents import DocumentIndex



FIXTURES = Path(__file__).with_name("fixtures")


class CorpusTests(unittest.TestCase):

    def setUp(self):
        global CaseCorpus
        from domain.ingestion.corpus import CaseCorpus
    def test_text_and_mbox_messages_have_stable_ids_and_hashes(self):
        corpus = CaseCorpus(FIXTURES, access_scope="matter-a")
        first = corpus.scan()
        second = corpus.scan()
        self.assertEqual(first, second)
        self.assertEqual(len(first), 2)
        self.assertEqual({item.media_type for item in first}, {"text/plain", "message/rfc822"})
        self.assertTrue(all(len(item.content_sha256) == 64 for item in first))
        self.assertTrue(all(item.access_scope == "matter-a" for item in first))

    def test_platform_injection_is_idempotent(self):
        corpus = CaseCorpus(FIXTURES)
        index = DocumentIndex(chunk_size=80, overlap=8)
        first = corpus.inject(index)
        second = corpus.inject(index)
        self.assertEqual(first, second)
        self.assertGreaterEqual(sum(item.chunk_count for item in first), 2)


if __name__ == "__main__":
    unittest.main()

