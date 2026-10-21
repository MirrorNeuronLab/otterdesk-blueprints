from copy import deepcopy
import json
from pathlib import Path
import re
import shutil
import tempfile
import unittest

from support import ROOT, RGX, configuration


class KnowledgeContracts(unittest.TestCase):



    def test_large_query_rows_cannot_evict_support_and_counter_source(self):
        session = QuerySession.__new__(QuerySession)
        session.evidence = {
            eid: {'id': eid, 'path': 'src/payment.py', 'line_start': 1, 'line_end': 10,
                  'kind': 'source', 'text': text}
            for eid, text in [('E1', 'charge()\n' * 100), ('E2', 'deduplicate()\n' * 100)]}
        receipts = [
            {'id': 'Q1', 'tool': 'calls', 'status': 'ok', 'params': {}, 'rows': [{'caller': 'x' * 4000}]},
            {'id': 'Q2', 'tool': 'inbound_count', 'status': 'ok', 'params': {}, 'rows': [{'inbound_dependency_pairs': 147}]},
            *[{'id': f'Q{i+3}', 'tool': 'semantic', 'status': 'ok', 'params': {}, 'search_text': role,
               'purpose': role, 'rows': [{'evidence_id': eid}]} for i, (eid, role) in enumerate([('E1', 'support'), ('E2', 'counter')])]]
        packet = session.packet(receipts, 2600)
        self.assertLessEqual(len(json.dumps(packet, ensure_ascii=False).encode()), 2600)
        self.assertEqual({p['purpose'] for p in packet['passages']}, {'support', 'counter'})
        self.assertTrue(all(p['excerpt_truncated'] for p in packet['passages']))
        self.assertEqual(packet['queries'][0]['rows'], [])
        self.assertEqual(packet['queries'][0]['rows_omitted'], 1)
        self.assertEqual(packet['queries'][1]['rows'], [{'inbound_dependency_pairs': 147}])
        self.assertEqual([q['id'] for q in packet['queries']], ['Q1', 'Q2', 'Q3', 'Q4'])
        self.assertGreater(packet['omitted_items'], 0)


import pytest

@pytest.fixture(autouse=True)
def bind_domain(architecture_paths):
    global QuerySession
    from domain.graph import QuerySession
