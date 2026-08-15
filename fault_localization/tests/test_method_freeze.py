"""Tests that the preregistered FL-v1 implementation remains frozen."""

import hashlib
import json
import unittest

from benchmark.config import PROJECT_ROOT


class MethodFreezeTests(unittest.TestCase):
    def test_fl_v1_metadata_and_implementation_hashes(self) -> None:
        path = PROJECT_ROOT / "benchmark" / "metadata" / "fl_method_v1.json"
        method = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual("fl-v1", method["method_version"])
        self.assertTrue(method["frozen_before_evaluation_selection"])
        self.assertFalse(method["tuning"]["evaluation_set_may_change_method"])
        for relative, expected in method["implementation"].items():
            digest = hashlib.sha256((PROJECT_ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(expected, digest, relative)


if __name__ == "__main__":
    unittest.main()
