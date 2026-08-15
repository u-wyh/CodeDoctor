"""Tests that the preregistered FL-v1 implementation remains frozen."""

import unittest

from fault_localization.method_freeze import validate_frozen_method


class MethodFreezeTests(unittest.TestCase):
    def test_fl_v1_metadata_and_implementation_hashes(self) -> None:
        method = validate_frozen_method()

        self.assertEqual("fl-v1", method["method_version"])
        self.assertTrue(method["frozen_before_evaluation_selection"])
        self.assertFalse(method["tuning"]["evaluation_set_may_change_method"])


if __name__ == "__main__":
    unittest.main()
