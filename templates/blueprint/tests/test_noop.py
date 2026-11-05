"""Run with python3.12 -m unittest discover -s tests -v."""

import importlib.util
import unittest
from pathlib import Path


class NoopTest(unittest.TestCase):
    def test_empty_operation_needs_no_context_services(self):
        path = Path(__file__).resolve().parents[1] / "payloads/domain/noop.py"
        spec = importlib.util.spec_from_file_location("blueprint_noop", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.run(object(), {}), {})


if __name__ == "__main__":
    unittest.main()
